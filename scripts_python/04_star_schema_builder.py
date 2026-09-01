"""
=============================================================================
 PHASE 3 — STAR SCHEMA DATA MODELING
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 Goal : Transform the normalized OLTP tables (8 tables) into an optimized
        Star Schema for Power BI analytics. This creates:

        2 Fact Tables  → Fact_Orders (one row per order)
                         Fact_Order_Items (one row per order item)
        4 Dim Tables   → Dim_Date, Dim_Customers, Dim_Products, Dim_Sellers

 WHY STAR SCHEMA?
   The raw Olist data follows 3NF normalization (OLTP) — great for
   transactions but TERRIBLE for analytics:
     - Too many JOINs slow down Power BI's VertiPaq engine
     - Circular dependencies cause ambiguous filter propagation
     - Complex relationships confuse DAX calculations
   
   Star Schema fixes all of this:
     - Separate order and order-item facts at their natural grains
     - All relationships are 1-to-Many (Dim → Fact)
     - Filters flow in ONE direction (Dim → Fact)
     - Power BI VertiPaq compresses Star Schema 5-10x better

 Output : CSV files in /data/star_schema/ ready for Power BI import
          + loaded into SQL Server [OlistEcommerce] database
=============================================================================
"""

import pandas as pd
import numpy as np
import os
from sqlalchemy import create_engine
from urllib.parse import quote_plus
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# 0. CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "data", "cleaned")
STAR_DIR = os.path.join(PROJECT_ROOT, "data", "star_schema")
os.makedirs(STAR_DIR, exist_ok=True)

# SQL Server connection
SERVER = r"localhost\SQLEXPRESS"
DATABASE = "OlistEcommerce"
DRIVER = "ODBC Driver 18 for SQL Server"
conn_str = (
    f"mssql+pyodbc://@{SERVER}/{DATABASE}"
    f"?driver={quote_plus(DRIVER)}"
    f"&TrustServerCertificate=yes"
    f"&Trusted_Connection=yes"
)
# Set OLIST_LOAD_TO_SQL=0 when validating the transformation locally without
# a running SQL Server instance. SQL loading remains enabled by default.
LOAD_TO_SQL = os.getenv("OLIST_LOAD_TO_SQL", "1").strip().lower() not in {
    "0", "false", "no"
}
engine = (
    create_engine(conn_str, fast_executemany=True)
    if LOAD_TO_SQL
    else None
)

# ──────────────────────────────────────────────────────────────────────────────
# 1. LOAD CLEANED DATA
# ──────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print(" LOADING CLEANED DATA ".center(80, "="))
print("=" * 80)

orders = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_orders.csv"),
                     parse_dates=["order_purchase_timestamp", "order_approved_at",
                                  "order_delivered_carrier_date",
                                  "order_delivered_customer_date",
                                  "order_estimated_delivery_date"])
order_items = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_order_items.csv"),
                          parse_dates=["shipping_limit_date"])
payments = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_payments.csv"))
reviews = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_reviews.csv"),
                      parse_dates=["review_creation_date", "review_answer_timestamp"])
products = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_products.csv"))
customers = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_customers.csv"))
sellers = pd.read_csv(os.path.join(CLEAN_DIR, "cleaned_sellers.csv"))

print("  All cleaned tables loaded.\n")

# ==========================================================================
# 2. BUILD DIM_DATE — THE MOST CRITICAL DIMENSION TABLE
# ==========================================================================
# WHY:
#   Power BI REQUIRES a continuous, unbroken date table for Time Intelligence
#   functions (YTD, MoM, SAMEPERIODLASTYEAR). Without it, these functions
#   silently return wrong results or errors.
#
# RULES:
#   - Must cover the FULL date range (Jan 2016 → Dec 2018)
#   - Must have NO gaps (every single day, even holidays with 0 orders)
#   - Must include decomposed date parts (Year, Quarter, Month, etc.)
#   - Will be marked as a "Date table" in Power BI settings
# ==========================================================================
print("Building Dim_Date...")

# Find the actual date range in the orders data
min_date = orders['order_purchase_timestamp'].min()
max_date = orders['order_purchase_timestamp'].max()
print(f"  Order date range: {min_date.date()} to {max_date.date()}")

# Create a continuous date range covering full years
# Start from Jan 1 of the earliest year, end Dec 31 of the latest year
start_date = pd.Timestamp(f"{min_date.year}-01-01")
end_date = pd.Timestamp(f"{max_date.year}-12-31")

# Generate every single date in the range
date_range = pd.date_range(start=start_date, end=end_date, freq='D')

dim_date = pd.DataFrame({'date': date_range})

# Decompose each date into useful components for Power BI slicers/filters
dim_date['date_key'] = dim_date['date'].dt.strftime('%Y%m%d').astype(int)  # Surrogate key: 20170101
dim_date['year'] = dim_date['date'].dt.year
dim_date['quarter'] = dim_date['date'].dt.quarter
dim_date['quarter_name'] = 'Q' + dim_date['quarter'].astype(str)  # "Q1", "Q2", etc.
dim_date['month'] = dim_date['date'].dt.month
dim_date['month_name'] = dim_date['date'].dt.strftime('%B')       # "January", "February", etc.
dim_date['month_short'] = dim_date['date'].dt.strftime('%b')      # "Jan", "Feb", etc.
dim_date['year_month'] = dim_date['date'].dt.strftime('%Y-%m')    # "2017-01" for sorting
dim_date['week'] = dim_date['date'].dt.isocalendar().week.astype(int)
dim_date['day_of_week'] = dim_date['date'].dt.dayofweek           # 0=Monday, 6=Sunday
dim_date['day_name'] = dim_date['date'].dt.strftime('%A')         # "Monday", "Tuesday", etc.
dim_date['day_of_month'] = dim_date['date'].dt.day
dim_date['is_weekend'] = dim_date['day_of_week'].isin([5, 6]).astype(int)

print(f"  Dim_Date: {len(dim_date):,} rows ({start_date.date()} to {end_date.date()})")

# ==========================================================================
# 3. BUILD DIM_CUSTOMERS — ONE ROW PER UNIQUE CUSTOMER
# ==========================================================================
# WHY:
#   The raw customers table has one row per TRANSACTION (customer_id changes
#   each purchase). For a Dimension table, we need ONE row per REAL customer
#   (customer_unique_id). This enables accurate customer counts and avoids
#   double-counting in Power BI visuals.
# ==========================================================================
print("Building Dim_Customers...")

# For customers who made multiple purchases, take the MOST RECENT location
# (they may have moved). Sort by most recent order first.
customer_orders = customers.merge(
    orders[['customer_id', 'order_purchase_timestamp']],
    on='customer_id', how='left'
)
customer_orders = customer_orders.sort_values('order_purchase_timestamp', ascending=False)

# Keep only the first (most recent) record per unique customer
dim_customers = customer_orders.drop_duplicates(
    subset='customer_unique_id', keep='first'
)[['customer_unique_id', 'customer_zip_code_prefix', 'customer_city', 'customer_state']]

# Clean city names — capitalize for professional presentation
dim_customers['customer_city'] = dim_customers['customer_city'].str.title()

print(f"  Dim_Customers: {len(dim_customers):,} unique customers")

# ==========================================================================
# 4. BUILD DIM_PRODUCTS — ONE ROW PER PRODUCT
# ==========================================================================
# This is mostly the cleaned products table, but we ensure:
#   - English category names are the primary category field
#   - Physical dimensions are clean for freight analysis
# ==========================================================================
print("Building Dim_Products...")

dim_products = products[[
    'product_id',
    'product_category_name_english',
    'product_weight_g',
    'product_length_cm',
    'product_height_cm',
    'product_width_cm'
]].copy()

# Rename for clarity in Power BI
dim_products = dim_products.rename(columns={
    'product_category_name_english': 'category'
})

# Calculate product volume (useful for shipping cost analysis)
dim_products['volume_cm3'] = (
    dim_products['product_length_cm'] *
    dim_products['product_height_cm'] *
    dim_products['product_width_cm']
)

print(f"  Dim_Products: {len(dim_products):,} products, {dim_products['category'].nunique()} categories")

# ==========================================================================
# 5. BUILD DIM_SELLERS — ONE ROW PER SELLER
# ==========================================================================
print("Building Dim_Sellers...")

dim_sellers = sellers[['seller_id', 'seller_zip_code_prefix',
                       'seller_city', 'seller_state']].copy()
dim_sellers['seller_city'] = dim_sellers['seller_city'].str.title()

print(f"  Dim_Sellers: {len(dim_sellers):,} sellers")

# ===========================================================================
# 6. PREPARE ORDER-LEVEL REVIEWS AND PAYMENTS
# ===========================================================================
# Reviews are not guaranteed to be unique by order_id. Joining them directly
# to order items previously duplicated order-item rows. Keep the latest
# answered review per order, with stable tie-breakers for reproducibility.
review_one_per_order = (
    reviews[[
        'order_id', 'review_id', 'review_score',
        'review_creation_date', 'review_answer_timestamp'
    ]]
    .sort_values(
        ['order_id', 'review_answer_timestamp', 'review_creation_date', 'review_id'],
        ascending=[True, False, False, True],
        na_position='last'
    )
    .drop_duplicates(subset='order_id', keep='first')
)

duplicate_review_rows_removed = len(reviews) - len(review_one_per_order)
print(f"Prepared reviews: {len(review_one_per_order):,} unique orders "
      f"({duplicate_review_rows_removed:,} duplicate rows resolved)")

# Aggregate payment values to one row per order. Define the primary payment
# type as the payment row with the largest value instead of relying on source
# row order.
payment_summary = payments.groupby('order_id', as_index=False).agg(
    total_payment=('payment_value', 'sum'),
    payment_installments_max=('payment_installments', 'max')
)
primary_payment = (
    payments
    .sort_values(
        ['order_id', 'payment_value', 'payment_sequential', 'payment_type'],
        ascending=[True, False, True, True],
        na_position='last'
    )
    .drop_duplicates(subset='order_id', keep='first')
    [['order_id', 'payment_type']]
    .rename(columns={'payment_type': 'payment_type_primary'})
)
payment_one_per_order = payment_summary.merge(
    primary_payment,
    on='order_id',
    how='left',
    validate='one_to_one'
)

# ===========================================================================
# 7. BUILD FACT_ORDERS — ONE ROW PER ORDER
# ===========================================================================
print("Building Fact_Orders...")

fact_orders = orders.merge(
    customers[['customer_id', 'customer_unique_id']],
    on='customer_id',
    how='left',
    validate='one_to_one'
)
fact_orders = fact_orders.merge(
    review_one_per_order[['order_id', 'review_score']],
    on='order_id',
    how='left',
    validate='one_to_one'
)
fact_orders = fact_orders.merge(
    payment_one_per_order,
    on='order_id',
    how='left',
    validate='one_to_one'
)

fact_orders['order_date_key'] = (
    fact_orders['order_purchase_timestamp']
    .dt.strftime('%Y%m%d')
    .astype('Int64')
)
fact_orders['delivery_days'] = (
    fact_orders['order_delivered_customer_date']
    - fact_orders['order_purchase_timestamp']
).dt.days
fact_orders['delivery_delay_days'] = (
    fact_orders['order_delivered_customer_date']
    - fact_orders['order_estimated_delivery_date']
).dt.days

# Preserve unknown/not-delivered orders as NULL. They must not be classified
# as on-time deliveries.
fact_orders['is_late_delivery'] = pd.Series(
    pd.NA,
    index=fact_orders.index,
    dtype='Int64'
)
known_delivery = fact_orders['delivery_delay_days'].notna()
fact_orders.loc[known_delivery, 'is_late_delivery'] = (
    fact_orders.loc[known_delivery, 'delivery_delay_days'] > 0
).astype('Int64')

fact_orders_final = fact_orders[[
    'order_id', 'order_date_key', 'customer_unique_id', 'order_status',
    'total_payment', 'payment_installments_max', 'payment_type_primary',
    'delivery_days', 'delivery_delay_days', 'is_late_delivery', 'review_score',
    'order_purchase_timestamp', 'order_approved_at',
    'order_delivered_carrier_date', 'order_delivered_customer_date',
    'order_estimated_delivery_date'
]].copy()

print(f"  Fact_Orders: {len(fact_orders_final):,} rows, "
      f"{fact_orders_final.shape[1]} columns")

# ===========================================================================
# 8. BUILD FACT_ORDER_ITEMS — ONE ROW PER ORDER ITEM
# ==========================================================================
# WHY THIS IS THE HEART OF THE STAR SCHEMA:
#   Each row = one product item in one order = the finest grain of a sale.
#   This table holds all the MEASURABLE business metrics:
#     - price, freight_value (revenue measures)
#     - delivery timing (operational measures)
#     - review_score (satisfaction measure)
#   Plus FOREIGN KEYS pointing to all Dimension tables for slicing/dicing.
#
# GRAIN: One row per order_item (order_id + order_item_id combination)
# ==========================================================================
print("Building Fact_Order_Items...")

# Start with order_items as the base (finest grain)
fact = order_items[['order_id', 'order_item_id', 'product_id',
                    'seller_id', 'price', 'freight_value']].copy()

# ── JOIN 1: Orders table → brings in customer_id, dates, status ──
fact = fact.merge(
    orders[['order_id', 'customer_id', 'order_status',
            'order_purchase_timestamp', 'order_approved_at',
            'order_delivered_carrier_date', 'order_delivered_customer_date',
            'order_estimated_delivery_date']],
    on='order_id', how='left', validate='many_to_one'
)

# ── JOIN 2: Customers → brings in customer_unique_id (the real FK for Dim) ──
fact = fact.merge(
    customers[['customer_id', 'customer_unique_id']],
    on='customer_id', how='left', validate='many_to_one'
)

# ── JOIN 3: Reviews → one deterministic review per order ──
fact = fact.merge(
    review_one_per_order[['order_id', 'review_score']],
    on='order_id', how='left', validate='many_to_one'
)

# ── JOIN 4: Payments → one aggregated payment record per order ──
fact = fact.merge(
    payment_one_per_order,
    on='order_id', how='left', validate='many_to_one'
)

# ── DERIVED METRICS ──
# These pre-calculated columns speed up Power BI because DAX doesn't
# need to compute them at query time

# Date key for joining to Dim_Date (format: YYYYMMDD as integer)
fact['order_date_key'] = fact['order_purchase_timestamp'].dt.strftime('%Y%m%d').astype('Int64')

# Total revenue per line item (product price + shipping)
fact['line_total'] = fact['price'] + fact['freight_value']

# Delivery time in days (NULL if not delivered)
fact['delivery_days'] = (
    fact['order_delivered_customer_date'] - fact['order_purchase_timestamp']
).dt.days

# Delivery delay: positive = late, negative = early, 0 = on time
fact['delivery_delay_days'] = (
    fact['order_delivered_customer_date'] - fact['order_estimated_delivery_date']
).dt.days

# Was the delivery late? Preserve missing delivery outcomes as NULL.
fact['is_late_delivery'] = pd.Series(pd.NA, index=fact.index, dtype='Int64')
known_item_delivery = fact['delivery_delay_days'].notna()
fact.loc[known_item_delivery, 'is_late_delivery'] = (
    fact.loc[known_item_delivery, 'delivery_delay_days'] > 0
).astype('Int64')

# Select final columns for the Fact table
fact_final = fact[[
    # Keys
    'order_id', 'order_item_id', 'order_date_key',
    'customer_unique_id', 'product_id', 'seller_id',
    # Status
    'order_status',
    # Measures — Revenue
    'price', 'freight_value', 'line_total',
    'total_payment', 'payment_installments_max', 'payment_type_primary',
    # Measures — Operations
    'delivery_days', 'delivery_delay_days', 'is_late_delivery',
    # Measures — Satisfaction
    'review_score',
    # Timestamps (for drill-through if needed)
    'order_purchase_timestamp', 'order_delivered_customer_date',
    'order_estimated_delivery_date'
]].copy()

print(f"  Fact_Order_Items: {len(fact_final):,} rows, {fact_final.shape[1]} columns")
print(f"    Revenue columns: price, freight_value, line_total, total_payment")
print(f"    Ops columns:     delivery_days, delivery_delay_days, is_late_delivery")
print(f"    FK columns:      customer_unique_id, product_id, seller_id, order_date_key")

# ===========================================================================
# 9. DATA QUALITY GATES
# ===========================================================================
print("\n" + "=" * 80)
print(" DATA QUALITY GATES ".center(80, "="))
print("=" * 80)

assert fact_orders_final['order_id'].is_unique, \
    "Fact_Orders must contain exactly one row per order_id"
assert len(fact_orders_final) == len(orders), \
    "Fact_Orders row count must match the cleaned orders table"
assert not fact_final.duplicated(['order_id', 'order_item_id']).any(), \
    "Fact_Order_Items contains duplicate business keys"
assert len(fact_final) == len(order_items), \
    "Fact_Order_Items row count must match cleaned order_items"
assert review_one_per_order['order_id'].is_unique, \
    "Review preparation did not produce one row per order"
assert payment_one_per_order['order_id'].is_unique, \
    "Payment preparation did not produce one row per order"

assert fact_final['order_id'].isin(fact_orders_final['order_id']).all(), \
    "Fact_Order_Items contains order IDs missing from Fact_Orders"
assert fact_final['product_id'].isin(dim_products['product_id']).all(), \
    "Fact_Order_Items contains product IDs missing from Dim_Products"
assert fact_final['seller_id'].isin(dim_sellers['seller_id']).all(), \
    "Fact_Order_Items contains seller IDs missing from Dim_Sellers"
assert fact_orders_final['customer_unique_id'].isin(
    dim_customers['customer_unique_id']
).all(), "Fact_Orders contains customer IDs missing from Dim_Customers"

source_revenue = (order_items['price'] + order_items['freight_value']).sum()
fact_revenue = fact_final['line_total'].sum()
assert np.isclose(source_revenue, fact_revenue, rtol=0, atol=0.01), \
    "Fact item revenue does not reconcile with cleaned order items"

unknown_delivery = fact_orders_final['delivery_delay_days'].isna()
assert fact_orders_final.loc[unknown_delivery, 'is_late_delivery'].isna().all(), \
    "Unknown deliveries must keep a NULL late-delivery flag"
assert fact_orders_final.loc[~unknown_delivery, 'is_late_delivery'].notna().all(), \
    "Known deliveries must have a late-delivery flag"

print(f"  [PASS] Fact_Orders unique key:       {len(fact_orders_final):>10,} rows")
print(f"  [PASS] Fact_Order_Items unique key:  {len(fact_final):>10,} rows")
print(f"  [PASS] Revenue reconciliation:       R$ {fact_revenue:,.2f}")
print(f"  [PASS] Unknown delivery flags:       {unknown_delivery.sum():>10,} NULL")
print("  [PASS] Dimension foreign keys:       no orphan keys")

# ===========================================================================
# 10. EXPORT TO CSV (for Power BI import)
# ==========================================================================
print("\n" + "=" * 80)
print(" EXPORTING STAR SCHEMA TO CSV ".center(80, "="))
print("=" * 80)

export_map = {
    "Fact_Orders.csv":      fact_orders_final,
    "Fact_Order_Items.csv": fact_final,
    "Dim_Date.csv":         dim_date,
    "Dim_Customers.csv":    dim_customers,
    "Dim_Products.csv":     dim_products,
    "Dim_Sellers.csv":      dim_sellers,
}

for filename, df in export_map.items():
    filepath = os.path.join(STAR_DIR, filename)
    df.to_csv(filepath, index=False)
    print(f"  {filename:<30} -> {df.shape[0]:>10,} rows x {df.shape[1]:>3} cols")

# ==========================================================================
# 11. OPTIONALLY LOAD INTO SQL SERVER
# ==========================================================================
print("\n" + "=" * 80)
print(" LOADING STAR SCHEMA INTO SQL SERVER ".center(80, "="))
print("=" * 80)

sql_map = {
    "Fact_Orders":      fact_orders_final,
    "Fact_Order_Items": fact_final,
    "Dim_Date":         dim_date,
    "Dim_Customers":    dim_customers,
    "Dim_Products":     dim_products,
    "Dim_Sellers":      dim_sellers,
}

if LOAD_TO_SQL:
    for table_name, df in sql_map.items():
        print(f"  Loading {table_name}...")
        df.to_sql(name=table_name, con=engine, if_exists='replace',
                  index=False, chunksize=1000)
        print(f"    Done ({df.shape[0]:,} rows)")
else:
    print("  Skipped because OLIST_LOAD_TO_SQL=0")

# ==========================================================================
# 12. VERIFICATION
# ==========================================================================
print("\n" + "=" * 80)
print(" STAR SCHEMA SUMMARY ".center(80, "="))
print("=" * 80)

print("""
  STAR SCHEMA ARCHITECTURE:

  Dim_Date -----------+---- Fact_Orders ---- Dim_Customers
                      |
                      +---- Fact_Order_Items ---- Dim_Products
                                    |
                               Dim_Sellers

  Fact_Orders grain:      one row per order_id
  Fact_Order_Items grain: one row per (order_id, order_item_id)
  Relationship direction: Dimension -> Fact
""")

print("  Table sizes:")
for name, df in sql_map.items():
    print(f"    {name:<25} {df.shape[0]:>10,} rows x {df.shape[1]:>3} cols")

print("\n  Order-item measures:")
for measure in ['price', 'freight_value', 'line_total']:
    non_null = fact_final[measure].notna().sum()
    print(f"    {measure:<30} non-null={non_null:>10,}")

print("\n  Order-level measures:")
for measure in [
    'total_payment', 'delivery_days', 'delivery_delay_days',
    'is_late_delivery', 'review_score'
]:
    non_null = fact_orders_final[measure].notna().sum()
    print(f"    {measure:<30} non-null={non_null:>10,}")

print("\n" + "=" * 80)
print(" STAR SCHEMA BUILD COMPLETE ".center(80, "="))
print("=" * 80)
print(f"\n  CSV files: {STAR_DIR}")
if LOAD_TO_SQL:
    print(f"  SQL tables: {SERVER} / {DATABASE}")
else:
    print("  SQL load: skipped")
print("  Phase 1 data-quality gates passed.\n")
