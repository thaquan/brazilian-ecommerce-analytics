"""
=============================================================================
 PHASE 1 — STEP 2: DATA CLEANING
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 Goal : Clean all raw CSV files through a systematic 5-step process:
        1) Cast datetime columns (object → datetime64)
        2) Handle missing values using business-logic strategies (MNAR)
        3) Translate product category names (Portuguese → English)
        4) Detect & flag statistical outliers via IQR method
        5) Export cleaned datasets ready for SQL import & Power BI modeling

 Input : Raw CSV files from /data/raw/
 Output: Cleaned CSV files to /data/cleaned/
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import seaborn as sns
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# 0. CONFIGURATION — Resolve paths relative to THIS script's location
#    os.path.dirname(__file__)     → /scripts_python/
#    os.path.dirname(dirname...)   → /Brazilian E-Commerce/  (project root)
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
CLEAN_DIR = os.path.join(PROJECT_ROOT, "data", "cleaned")

# Create output directory if it doesn't exist yet
os.makedirs(CLEAN_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1. LOAD ALL RAW DATA TABLES
#    We load every table that will be part of the Star Schema later.
#    Tables that don't need heavy cleaning (customers, sellers, geolocation)
#    still pass through the pipeline to ensure consistent export format.
# ──────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print(" LOADING RAW DATA FILES ".center(80, "="))
print("=" * 80)

orders     = pd.read_csv(os.path.join(RAW_DIR, "olist_orders_dataset.csv"))
order_items = pd.read_csv(os.path.join(RAW_DIR, "olist_order_items_dataset.csv"))
payments   = pd.read_csv(os.path.join(RAW_DIR, "olist_order_payments_dataset.csv"))
reviews    = pd.read_csv(os.path.join(RAW_DIR, "olist_order_reviews_dataset.csv"))
products   = pd.read_csv(os.path.join(RAW_DIR, "olist_products_dataset.csv"))
customers  = pd.read_csv(os.path.join(RAW_DIR, "olist_customers_dataset.csv"))
sellers    = pd.read_csv(os.path.join(RAW_DIR, "olist_sellers_dataset.csv"))
geolocation = pd.read_csv(os.path.join(RAW_DIR, "olist_geolocation_dataset.csv"))
translation = pd.read_csv(os.path.join(RAW_DIR, "product_category_name_translation.csv"))

# Quick overview of what we loaded
tables = {
    "orders": orders, "order_items": order_items, "payments": payments,
    "reviews": reviews, "products": products, "customers": customers,
    "sellers": sellers, "geolocation": geolocation
}
for name, df in tables.items():
    print(f"  Loaded {name:<15} -> {df.shape[0]:>10,} rows x {df.shape[1]:>3} cols")

print(f"\n{'─' * 80}")
print(" START DATA CLEANING PROCESS ".center(80, "─"))
print(f"{'─' * 80}\n")

# ==========================================================================
# STEP 1: CASTING DATETIME COLUMNS
# ==========================================================================
# WHY: pandas reads CSV date columns as plain strings (dtype: object).
#      Without explicit conversion to datetime64, we CANNOT perform:
#        - Time-series analysis (monthly trends, YoY growth)
#        - Date arithmetic (delivery_time = delivered - purchased)
#        - Extraction of components (year, month, day_of_week)
#      This is the FIRST thing to fix because all downstream time-based
#      analyses depend on proper datetime types.
# ==========================================================================
print("STEP 1/5: Casting datetime columns (object -> datetime64)...")

# --- Orders table: 5 timestamp columns ---
# These columns track the full lifecycle of an order:
#   purchase -> approval -> carrier pickup -> customer delivery -> estimated date
datetime_cols_orders = [
    'order_purchase_timestamp',       # When customer placed the order
    'order_approved_at',              # When payment was approved
    'order_delivered_carrier_date',   # When seller handed to carrier
    'order_delivered_customer_date',  # When customer received the package
    'order_estimated_delivery_date'   # Original estimated delivery date
]

for col in datetime_cols_orders:
    # errors='coerce' converts unparseable values to NaT (Not a Time)
    # instead of crashing the entire script — safer for dirty real-world data
    orders[col] = pd.to_datetime(orders[col], errors='coerce')

# --- Order Items table: 1 timestamp column ---
# shipping_limit_date = deadline for the seller to ship the product
order_items['shipping_limit_date'] = pd.to_datetime(
    order_items['shipping_limit_date'], errors='coerce'
)

# --- Reviews table: 2 timestamp columns ---
# review_creation_date   = when the review survey was sent to customer
# review_answer_timestamp = when customer actually submitted the review
reviews['review_creation_date'] = pd.to_datetime(
    reviews['review_creation_date'], errors='coerce'
)
reviews['review_answer_timestamp'] = pd.to_datetime(
    reviews['review_answer_timestamp'], errors='coerce'
)

# Verify: print the new dtypes to confirm conversion worked
print("  Orders datetime columns:")
for col in datetime_cols_orders:
    print(f"    {col:<45} -> {orders[col].dtype}")
print(f"  order_items.shipping_limit_date             -> {order_items['shipping_limit_date'].dtype}")
print(f"  reviews.review_creation_date                -> {reviews['review_creation_date'].dtype}")
print(f"  reviews.review_answer_timestamp             -> {reviews['review_answer_timestamp'].dtype}")
print()

# ==========================================================================
# STEP 2: HANDLING MISSING VALUES
# ==========================================================================
# PHILOSOPHY: We do NOT blindly dropna() or fillna(mean). Each missing value
#   has a REASON (Missing Data Mechanism). Our strategy depends on the cause:
#
#   - MNAR (Missing Not At Random): The missingness IS the information
#     Example: No delivery date because order was canceled → KEEP as NaT
#
#   - MAR (Missing At Random): Missingness depends on another observed variable
#     Example: No review comment because customer was lazy → FILL with default
#
#   - MCAR (Missing Completely At Random): True random gaps
#     Example: 2 products missing weight → FILL with median
# ==========================================================================
print("STEP 2/5: Handling missing values...")

# ── 2.1 Orders Table ──────────────────────────────────────────────────────
# STRATEGY: KEEP NULL (do nothing)
# REASONING: Cross-check from profiling proved that missing delivery dates
#   correspond to orders with status: canceled (550), unavailable (609),
#   shipped-but-not-yet-delivered (1,107), processing (301), etc.
#   These NaT values are NOT errors — they are business facts.
#   Imputing a fake delivery date would create "ghost shipments" and
#   corrupt our logistics KPIs (avg delivery time, on-time rate).
print("  2.1 Orders: Keeping NaT in delivery columns (MNAR — business status)")
print(f"      order_delivered_carrier_date  NaT count: {orders['order_delivered_carrier_date'].isna().sum():,}")
print(f"      order_delivered_customer_date NaT count: {orders['order_delivered_customer_date'].isna().sum():,}")
print(f"      order_approved_at            NaT count: {orders['order_approved_at'].isna().sum():,}")

# ── 2.2 Reviews Table ─────────────────────────────────────────────────────
# STRATEGY: Fill text columns with default string "No comment provided"
# REASONING: ~88% of reviews have no title, ~59% have no message body.
#   This is normal consumer behavior — most people just tap a star rating
#   without writing text. Filling with a readable default:
#     a) Prevents NaN errors in text processing / NLP pipelines
#     b) Preserves the review_score (the actual signal of satisfaction)
#     c) Makes data consistent for downstream GROUP BY / filtering
print("  2.2 Reviews: Filling missing comment text with default string")
reviews['review_comment_title'] = reviews['review_comment_title'].fillna('No comment provided')
reviews['review_comment_message'] = reviews['review_comment_message'].fillna('No comment provided')
print(f"      review_comment_title   remaining NaN: {reviews['review_comment_title'].isna().sum()}")
print(f"      review_comment_message remaining NaN: {reviews['review_comment_message'].isna().sum()}")

# ── 2.3 Products Table ────────────────────────────────────────────────────
# STRATEGY A: Fill missing category with 'Others'
# REASONING: 610 products (1.85%) have no category. Instead of dropping them
#   (which would lose their revenue contribution in aggregations), we assign
#   a catch-all group 'Others'. This prevents GROUP BY errors while keeping
#   the products visible in the dataset.
print("  2.3 Products: Filling missing categories with 'Others'")
products['product_category_name'] = products['product_category_name'].fillna('Others')
print(f"      Remaining NaN in product_category_name: {products['product_category_name'].isna().sum()}")

# STRATEGY B: Fill missing dimensions with MEDIAN (2 products only)
# REASONING: Only 2 products out of 32,951 are missing physical dimensions.
#   Median is robust to outliers (unlike mean) and represents the "typical"
#   product size. This is a safe imputation for such a tiny fraction.
size_cols = ['product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm']
print("  2.3 Products: Filling missing dimensions with median values")
for col in size_cols:
    median_val = products[col].median()
    na_count = products[col].isna().sum()
    products[col] = products[col].fillna(median_val)
    print(f"      {col:<25} filled {na_count} NaN with median={median_val:.1f}")

# STRATEGY C: Fix zero-weight products
# REASONING: A product weighing exactly 0g is physically impossible for
#   e-commerce (even a sticker has weight). This is a data entry error.
#   Replacing with median preserves freight_value calculations downstream.
zero_weight_count = (products['product_weight_g'] == 0).sum()
if zero_weight_count > 0:
    weight_median = products.loc[products['product_weight_g'] > 0, 'product_weight_g'].median()
    products.loc[products['product_weight_g'] == 0, 'product_weight_g'] = weight_median
    print(f"  2.3 Products: Fixed {zero_weight_count} zero-weight products -> median={weight_median:.1f}g")

# ── 2.4 Customers Table ───────────────────────────────────────────────────
# STRATEGY: Ensure zip_code stays as STRING (not int)
# REASONING: Zip codes like "01001" would lose the leading zero if stored as
#   integer (becoming 1001). This breaks geolocation joins later.
customers['customer_zip_code_prefix'] = customers['customer_zip_code_prefix'].astype(str).str.zfill(5)
print("  2.4 Customers: Ensured zip_code_prefix is zero-padded string")

# ── 2.5 Sellers Table ─────────────────────────────────────────────────────
sellers['seller_zip_code_prefix'] = sellers['seller_zip_code_prefix'].astype(str).str.zfill(5)
print("  2.5 Sellers: Ensured zip_code_prefix is zero-padded string")

# ── 2.6 Geolocation Table ─────────────────────────────────────────────────
geolocation['geolocation_zip_code_prefix'] = geolocation['geolocation_zip_code_prefix'].astype(str).str.zfill(5)
print("  2.6 Geolocation: Ensured zip_code_prefix is zero-padded string")
print()

# ==========================================================================
# STEP 3: TRANSLATE PRODUCT CATEGORY NAMES (Portuguese → English)
# ==========================================================================
# WHY: The original dataset uses Portuguese category names (e.g. "beleza_saude").
#   For an international portfolio targeting English-speaking recruiters,
#   all categories must be in English. The translation file covers 71 of 73
#   categories — we manually add the 2 missing ones identified in profiling.
# ==========================================================================
print("STEP 3/5: Translating category names (Portuguese -> English)...")

# Add the 2 categories that the official translation file is missing
# These were identified in our Step 1 profiling script:
#   - pc_gamer → "PC Gamer" (self-explanatory gaming category)
#   - portateis_cozinha_e_preparadores_de_alimentos → long Portuguese name
#     for portable kitchen appliances and food processors
manual_translations = pd.DataFrame([
    {
        'product_category_name': 'pc_gamer',
        'product_category_name_english': 'PC Gamer'
    },
    {
        'product_category_name': 'portateis_cozinha_e_preparadores_de_alimentos',
        'product_category_name_english': 'Portable Kitchen and Food Processors'
    }
])

# Append our manual entries to the official dictionary
translation = pd.concat([translation, manual_translations], ignore_index=True)
print(f"  Translation dictionary: {len(translation)} categories (71 official + 2 manual)")

# Merge the English names into the products table via LEFT JOIN
# LEFT JOIN ensures no products are lost — unmatched rows get NaN
products = products.merge(translation, on='product_category_name', how='left')

# Products with category='Others' (our fill value) won't match any translation,
# so their English name will be NaN → fill with 'Others' to stay consistent
products['product_category_name_english'] = products['product_category_name_english'].fillna('Others')

# Verify: check for any remaining untranslated categories
untranslated = products[products['product_category_name_english'].isna()]['product_category_name'].unique()
if len(untranslated) > 0:
    print(f"  WARNING: {len(untranslated)} categories still untranslated: {untranslated}")
else:
    print("  All categories successfully translated to English")

# Show distribution of top 10 English categories
print("\n  Top 10 product categories (English):")
top_cats = products['product_category_name_english'].value_counts().head(10)
for cat, count in top_cats.items():
    print(f"    {cat:<45} {count:>6,} products")
print()

# ==========================================================================
# STEP 4: DETECT & FLAG OUTLIERS USING IQR METHOD
# ==========================================================================
# WHY: E-commerce data contains extreme values in price / freight / payment.
#   Some are genuine (luxury items, bulk orders), some are data entry errors.
#   We FLAG outliers with a boolean column instead of DELETING them, because:
#     a) Deleting real high-value transactions corrupts GMV calculations
#     b) Flagging lets analysts filter them IN or OUT depending on the analysis
#     c) It demonstrates business-aware data handling to recruiters
#
# METHOD: Interquartile Range (IQR)
#   Q1 = 25th percentile, Q3 = 75th percentile
#   IQR = Q3 - Q1
#   Outlier if value < Q1 - 1.5*IQR  OR  value > Q3 + 1.5*IQR
#   The 1.5x multiplier is the statistical standard (Tukey's fence)
# ==========================================================================
print("STEP 4/5: Detecting & flagging outliers (IQR method)...")


def flag_outliers_iqr(df, column_name):
    """
    Flag outliers in a numeric column using the IQR method.

    Adds a new boolean column '{column_name}_is_outlier' to the DataFrame.
    True = the value is a statistical outlier (outside Tukey's fences).

    Parameters:
        df          : pandas DataFrame
        column_name : name of the numeric column to analyze

    Returns:
        df          : same DataFrame with the new flag column added
    """
    Q1 = df[column_name].quantile(0.25)  # 25th percentile (lower quartile)
    Q3 = df[column_name].quantile(0.75)  # 75th percentile (upper quartile)
    IQR = Q3 - Q1                        # Interquartile Range = spread of middle 50%

    lower_bound = Q1 - 1.5 * IQR  # Values below this are unusually low
    upper_bound = Q3 + 1.5 * IQR  # Values above this are unusually high

    # Create boolean flag: True if the value falls outside the fences
    df[f'{column_name}_is_outlier'] = (
        (df[column_name] < lower_bound) | (df[column_name] > upper_bound)
    )

    # Print summary for transparency
    outlier_count = df[f'{column_name}_is_outlier'].sum()
    outlier_pct = outlier_count / len(df) * 100
    print(f"  {column_name:<25} Q1={Q1:>10,.2f}  Q3={Q3:>10,.2f}  "
          f"IQR={IQR:>10,.2f}  bounds=[{lower_bound:>10,.2f}, {upper_bound:>10,.2f}]  "
          f"outliers={outlier_count:>6,} ({outlier_pct:.2f}%)")

    return df


# Apply outlier flagging to the key financial columns
# These are the columns most likely to contain extreme values that could
# skew revenue calculations or logistics cost analysis
order_items = flag_outliers_iqr(order_items, 'price')          # Product selling price
order_items = flag_outliers_iqr(order_items, 'freight_value')  # Shipping cost per item
payments = flag_outliers_iqr(payments, 'payment_value')        # Total payment amount
print()

# ==========================================================================
# STEP 5: EXPORT CLEANED DATA
# ==========================================================================
# All cleaned tables are exported to /data/cleaned/ as CSV files.
# These files will be imported into:
#   - SQL database (PostgreSQL/BigQuery) for advanced queries in Phase 2
#   - Power BI for Star Schema modeling in Phase 3-4
# ==========================================================================
print("STEP 5/5: Exporting cleaned data...")

export_map = {
    "cleaned_orders.csv":      orders,
    "cleaned_order_items.csv": order_items,
    "cleaned_payments.csv":    payments,
    "cleaned_reviews.csv":     reviews,
    "cleaned_products.csv":    products,
    "cleaned_customers.csv":   customers,
    "cleaned_sellers.csv":     sellers,
    "cleaned_geolocation.csv": geolocation,
}

for filename, df in export_map.items():
    filepath = os.path.join(CLEAN_DIR, filename)
    df.to_csv(filepath, index=False)
    print(f"  Exported {filename:<30} -> {df.shape[0]:>10,} rows x {df.shape[1]:>3} cols")

# ==========================================================================
# VERIFICATION SUMMARY
# ==========================================================================
# Final sanity check: confirm that cleaning didn't accidentally drop rows
# or create unexpected NaN values in critical columns
# ==========================================================================
print("\n" + "=" * 80)
print(" POST-CLEANING VERIFICATION ".center(80, "="))
print("=" * 80)

print("\n  Row counts (raw vs cleaned — should be identical):")
raw_counts = {
    "orders": 99441, "order_items": 112650, "payments": 103886,
    "reviews": 99224, "products": 32951, "customers": 99441,
    "sellers": 3095, "geolocation": 1000163
}
for name, df in tables.items():
    raw_c = raw_counts.get(name, "?")
    status = "OK" if df.shape[0] == raw_c else "MISMATCH"
    print(f"    {name:<15} raw={raw_c:>10,}  cleaned={df.shape[0]:>10,}  [{status}]")

print("\n  Critical columns — remaining NaN check:")
critical_checks = [
    (orders, "orders",     "order_purchase_timestamp"),
    (orders, "orders",     "order_status"),
    (products, "products", "product_category_name_english"),
    (reviews, "reviews",   "review_score"),
]
for df, tbl, col in critical_checks:
    nan_count = df[col].isna().sum()
    status = "OK" if nan_count == 0 else f"WARNING: {nan_count:,} NaN"
    print(f"    {tbl}.{col:<40} [{status}]")

print("\n  Outlier flag summary:")
print(f"    order_items.price_is_outlier:         {order_items['price_is_outlier'].sum():>6,} / {len(order_items):,}")
print(f"    order_items.freight_value_is_outlier: {order_items['freight_value_is_outlier'].sum():>6,} / {len(order_items):,}")
print(f"    payments.payment_value_is_outlier:    {payments['payment_value_is_outlier'].sum():>6,} / {len(payments):,}")

print("\n" + "=" * 80)
print(" CLEANING PROCESS COMPLETED SUCCESSFULLY ".center(80, "="))
print("=" * 80)
print(f"\n  All {len(export_map)} cleaned files exported to: {CLEAN_DIR}")
print("  Ready for Phase 2 (SQL) and Phase 3-4 (Power BI Star Schema)\n")
