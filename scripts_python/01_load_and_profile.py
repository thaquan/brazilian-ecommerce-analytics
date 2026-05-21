"""
=============================================================================
 PHASE 1 — STEP 1: DATA LOADING & INITIAL PROFILING
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 Goal : Load all 8 raw CSV files, inspect their schema, data types, missing
        values, and produce a consolidated profiling summary.
        This report guides ALL cleaning decisions in Step 2.

 WHY THIS STEP MATTERS:
   Before writing ANY transformation code, a professional analyst must
   understand the raw data's "personality" — its shape, quirks, and gaps.
   Skipping this step is like performing surgery without reading the X-ray.

 Input : Raw CSV files from /data/raw/
 Output: Console report (no files created — this is a read-only inspection)
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# 1. CONFIGURATION
# ──────────────────────────────────────────────
# Build paths relative to this script's location so the script works
# regardless of which directory the user runs it from.
#   __file__                      = /scripts_python/01_load_and_profile.py
#   os.path.dirname(__file__)     = /scripts_python/
#   os.path.dirname(dirname...)   = /Brazilian E-Commerce/  (project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")

# Map of short names → actual CSV filenames for easier iteration
FILE_MAP = {
    "customers":    "olist_customers_dataset.csv",
    "orders":       "olist_orders_dataset.csv",
    "order_items":  "olist_order_items_dataset.csv",
    "products":     "olist_products_dataset.csv",
    "sellers":      "olist_sellers_dataset.csv",
    "payments":     "olist_order_payments_dataset.csv",
    "reviews":      "olist_order_reviews_dataset.csv",
    "geolocation":  "olist_geolocation_dataset.csv",
}

TRANSLATION_FILE = "product_category_name_translation.csv"

# ──────────────────────────────────────────────
# 2. LOAD ALL TABLES
# ──────────────────────────────────────────────
# Load every CSV into a dictionary of DataFrames.
# Using a dict makes it easy to iterate over all tables uniformly
# for profiling, instead of writing repetitive code for each table.
print("=" * 80)
print(" LOADING RAW DATA FILES ".center(80, "="))
print("=" * 80)

dataframes = {}
for name, filename in FILE_MAP.items():
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.read_csv(filepath)
    dataframes[name] = df
    print(f"  Loaded {name:<15} -> {df.shape[0]:>10,} rows x {df.shape[1]:>3} cols  |  {filename}")

# Load the Portuguese-to-English category translation table separately
# This file maps product_category_name (PT) → product_category_name_english (EN)
translation = pd.read_csv(os.path.join(DATA_DIR, TRANSLATION_FILE))
dataframes["translation"] = translation
print(f"  Loaded {'translation':<15} -> {translation.shape[0]:>10,} rows x {translation.shape[1]:>3} cols  |  {TRANSLATION_FILE}")

print(f"\n{'─' * 80}")
print(f" Total tables loaded: {len(dataframes)}")
print(f"{'─' * 80}\n")

# ──────────────────────────────────────────────
# 3. DATA PROFILING — SCHEMA & TYPES
# ──────────────────────────────────────────────
# For each table, we inspect:
#   - Shape (rows x columns) → understand volume
#   - Data types per column  → identify mis-typed columns
#     (especially timestamps stored as 'object' strings)
#   - Sample values          → sanity-check the actual content
print("=" * 80)
print(" DATA TYPE ANALYSIS ".center(80, "="))
print("=" * 80)

for name, df in dataframes.items():
    print(f"\n{'─' * 60}")
    print(f"  TABLE: {name.upper()}")
    print(f"{'─' * 60}")
    print(f"  Shape: {df.shape[0]:,} rows x {df.shape[1]} columns\n")

    # Count how many columns belong to each data type (object, int64, float64)
    # This quickly reveals if timestamps are stuck as 'object' (string)
    dtype_summary = df.dtypes.value_counts()
    print(f"  Data type distribution:")
    for dtype, count in dtype_summary.items():
        print(f"    {str(dtype):<15} -> {count} columns")

    # Show each column's name, type, and a sample value for quick inspection
    print(f"\n  Column details:")
    for col in df.columns:
        sample = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else 'N/A'
        print(f"    {col:<45} {str(df[col].dtype):<12} | sample: {sample}")

# ──────────────────────────────────────────────
# 4. MISSING VALUES ANALYSIS
# ──────────────────────────────────────────────
# This is the MOST IMPORTANT section of profiling.
# We identify WHICH columns have NaN and HOW MANY, so we can decide
# the correct handling strategy in Step 2 (keep, fill, or drop).
print("\n" + "=" * 80)
print(" MISSING VALUES ANALYSIS ".center(80, "="))
print("=" * 80)

for name, df in dataframes.items():
    # Count NaN per column and calculate the percentage
    missing = df.isnull().sum()
    missing_pct = (df.isnull().sum() / len(df) * 100).round(2)
    has_missing = missing[missing > 0]  # Filter to only columns with issues

    if len(has_missing) == 0:
        print(f"\n  {name.upper()}: No missing values detected.")
        continue

    # Display a formatted table of problematic columns
    print(f"\n  {name.upper()}: {len(has_missing)} column(s) with missing values")
    print(f"  {'Column':<45} {'Missing':>10} {'Pct (%)':>10}")
    print(f"  {'─' * 65}")
    for col in has_missing.index:
        print(f"  {col:<45} {missing[col]:>10,} {missing_pct[col]:>9.2f}%")

# ──────────────────────────────────────────────
# 5. SAMPLE ROWS (HEAD)
# ──────────────────────────────────────────────
# Visual inspection of the first few rows helps catch issues that
# statistics alone can't reveal: weird characters, mixed formats,
# empty strings disguised as non-null, etc.
print("\n" + "=" * 80)
print(" SAMPLE ROWS (FIRST 3) ".center(80, "="))
print("=" * 80)

for name, df in dataframes.items():
    print(f"\n{'─' * 60}")
    print(f"  {name.upper()} - first 3 rows:")
    print(f"{'─' * 60}")
    print(df.head(3).to_string(index=False, max_colwidth=40))

# ──────────────────────────────────────────────
# 6. KEY OBSERVATIONS — TIMESTAMP COLUMNS
# ──────────────────────────────────────────────
# Automatically detect columns that SHOULD be datetime (based on naming
# conventions like "timestamp", "date", "_at") and check if pandas
# correctly identified them or left them as 'object' (string).
# Any column flagged as "NEEDS CASTING" must be fixed in Step 2.
print("\n" + "=" * 80)
print(" TIMESTAMP COLUMNS DETECTION ".center(80, "="))
print("=" * 80)

timestamp_keywords = ["timestamp", "date", "_at"]
for name, df in dataframes.items():
    # Find columns whose names contain date-related keywords
    ts_cols = [c for c in df.columns if any(kw in c.lower() for kw in timestamp_keywords)]
    if ts_cols:
        print(f"\n  {name.upper()}:")
        for col in ts_cols:
            current_type = df[col].dtype
            sample_val = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else "N/A"
            # If dtype is 'object', it means pandas read it as a plain string
            # → we must cast it to datetime64 in Step 2
            status = "NEEDS CASTING" if current_type == "object" else "OK"
            print(f"    {col:<45} type={str(current_type):<10} [{status}]  | sample: {sample_val}")

# ──────────────────────────────────────────────
# 7. QUICK STATS FOR NUMERIC COLUMNS
# ──────────────────────────────────────────────
# describe() gives us min, max, mean, std, quartiles — essential to
# spot potential outliers BEFORE we decide how to handle them.
# We focus on tables with financial/physical measurements.
print("\n" + "=" * 80)
print(" NUMERIC COLUMNS - QUICK STATISTICS ".center(80, "="))
print("=" * 80)

numeric_tables = ["order_items", "payments", "products"]
for name in numeric_tables:
    df = dataframes[name]
    # Select only numeric columns (int64, float64)
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if num_cols:
        print(f"\n  {name.upper()}:")
        stats = df[num_cols].describe().round(2)
        print(stats.to_string())

# ──────────────────────────────────────────────
# 8. ORDER STATUS DISTRIBUTION
# ──────────────────────────────────────────────
# Understanding the breakdown of order statuses is critical because:
#   - 'delivered' orders are the basis for revenue/GMV calculations
#   - 'canceled'/'unavailable' explain why delivery dates are missing
#   - Low-frequency statuses ('created', 'approved') represent edge cases
print("\n" + "=" * 80)
print(" ORDER STATUS DISTRIBUTION ".center(80, "="))
print("=" * 80)

orders = dataframes["orders"]
status_counts = orders["order_status"].value_counts()
status_pct = (status_counts / len(orders) * 100).round(2)

print(f"\n  {'Status':<20} {'Count':>10} {'Pct (%)':>10}")
print(f"  {'─' * 40}")
for status, count in status_counts.items():
    print(f"  {status:<20} {count:>10,} {status_pct[status]:>9.2f}%")

# ──────────────────────────────────────────────
# 9. CROSS-CHECK: MISSING DELIVERY DATES vs STATUS
# ──────────────────────────────────────────────
# THIS IS THE KEY ANALYSIS that proves missing dates are MNAR:
# We look at WHICH order_status values have NULL delivery dates.
# If they're all 'canceled'/'shipped'/'processing', the nulls are
# expected business outcomes, NOT data quality issues.
print("\n" + "=" * 80)
print(" CROSS-CHECK: MISSING DELIVERY DATES vs ORDER STATUS ".center(80, "="))
print("=" * 80)

delivery_cols = [
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_approved_at"
]

for col in delivery_cols:
    missing_mask = orders[col].isnull()
    if missing_mask.sum() > 0:
        print(f"\n  Column: {col} ({missing_mask.sum():,} missing)")
        # Show which order statuses the missing values belong to
        cross = orders.loc[missing_mask, "order_status"].value_counts()
        for status, cnt in cross.items():
            print(f"    -> {status:<20} {cnt:>6,} rows")

# ──────────────────────────────────────────────
# 10. PRODUCT CATEGORY ANALYSIS
# ──────────────────────────────────────────────
# Check two things:
#   a) How many products have NO category at all? (need to fill with 'Others')
#   b) Do ALL existing Portuguese categories have an English translation?
#      If not, we must add manual translations in Step 2.
print("\n" + "=" * 80)
print(" PRODUCT CATEGORY - MISSING & TRANSLATION CHECK ".center(80, "="))
print("=" * 80)

products = dataframes["products"]
missing_cat = products["product_category_name"].isnull().sum()
total_cats = products["product_category_name"].nunique()
trans_cats = len(translation)

print(f"\n  Products with missing category: {missing_cat:,} / {len(products):,} ({missing_cat/len(products)*100:.2f}%)")
print(f"  Unique categories in products : {total_cats}")
print(f"  Categories in translation file: {trans_cats}")

# Find categories in the products table that DON'T exist in the translation file
existing_cats = set(products["product_category_name"].dropna().unique())
translated_cats = set(translation["product_category_name"].unique())
missing_trans = existing_cats - translated_cats  # Set difference

if missing_trans:
    print(f"\n  Categories WITHOUT translation ({len(missing_trans)}):")
    for cat in sorted(missing_trans):
        print(f"    * {cat}")
else:
    print(f"\n  All product categories have English translations available.")

# ──────────────────────────────────────────────
# PROFILING COMPLETE — SUMMARY OF NEXT STEPS
# ──────────────────────────────────────────────
print("\n" + "=" * 80)
print(" PROFILING COMPLETE ".center(80, "="))
print("=" * 80)
print("\n  Issues found — to be addressed in 02_data_cleaning.py:")
print("  1. Cast 8 timestamp columns from 'object' -> 'datetime64'")
print("  2. Handle missing values based on MNAR/MAR business logic")
print("  3. Translate product categories to English (+ 2 manual entries)")
print("  4. Detect and flag outliers in price / freight_value / payment_value")
print("  5. Ensure zip_code_prefix stays as zero-padded string")
print("  6. Export all cleaned CSVs to /data/cleaned/")
print()
