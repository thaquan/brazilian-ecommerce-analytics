"""
=============================================================================
 PHASE 2 — STEP 1: LOAD CLEANED DATA INTO SQL SERVER
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 Goal : Import all 8 cleaned CSV files into SQL Server Express as tables.
        This creates the relational database environment where we'll execute
        advanced SQL queries (CTEs, Window Functions, RFM analysis, Pareto).

 Connection: Windows Authentication (Trusted Connection) to local SQLEXPRESS
 Database  : OlistEcommerce
 Driver    : ODBC Driver 18 for SQL Server

 WHY SQL Server instead of just pandas?
   - Demonstrates real-world RDBMS skills (top requirement in 41% of JDs)
   - Enables JOIN across tables at database level (faster than pandas merge)
   - SQL queries are portable — same syntax works in BigQuery, PostgreSQL
   - Power BI connects natively to SQL Server for live dashboards
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import time
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONNECTION CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
# Connection string anatomy:
#   mssql+pyodbc://  → SQLAlchemy dialect for SQL Server via pyodbc
#   @localhost\SQLEXPRESS → local SQL Server Express instance
#   /OlistEcommerce  → target database name
#   driver=ODBC+Driver+18 → the ODBC driver version installed
#   TrustServerCertificate=yes → bypass SSL cert check (needed for ODBC 18)
#   Trusted_Connection=yes → use Windows Authentication (no password needed)

SERVER = r"localhost\SQLEXPRESS"
DATABASE = "OlistEcommerce"
DRIVER = "ODBC Driver 18 for SQL Server"

# Build the connection string — quote_plus handles special characters in the driver name
conn_str = (
    f"mssql+pyodbc://@{SERVER}/{DATABASE}"
    f"?driver={quote_plus(DRIVER)}"
    f"&TrustServerCertificate=yes"
    f"&Trusted_Connection=yes"
)

# Create the SQLAlchemy engine — this is the bridge between pandas and SQL Server
# fast_executemany=True dramatically speeds up bulk INSERT operations (10-50x faster)
engine = create_engine(conn_str, fast_executemany=True)

# ──────────────────────────────────────────────────────────────────────────────
# 2. TEST CONNECTION
# ──────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print(" CONNECTING TO SQL SERVER ".center(80, "="))
print("=" * 80)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@SERVERNAME AS server, DB_NAME() AS db"))
        row = result.fetchone()
        print(f"  Connected to: {row[0]} / {row[1]}")
        print(f"  Connection:   OK\n")
except Exception as e:
    print(f"  CONNECTION FAILED: {e}")
    print("\n  Troubleshooting:")
    print("    1. Is SQL Server Express running? Check: Get-Service MSSQL*")
    print("    2. Is the instance name correct? Default is SQLEXPRESS")
    print("    3. Is Windows Authentication enabled?")
    exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# 3. LOAD CLEANED CSVs
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "data", "cleaned")

# Define the mapping: SQL table name → CSV filename
# Table names use snake_case to match SQL conventions
TABLE_MAP = {
    "orders":       "cleaned_orders.csv",
    "order_items":  "cleaned_order_items.csv",
    "payments":     "cleaned_payments.csv",
    "reviews":      "cleaned_reviews.csv",
    "products":     "cleaned_products.csv",
    "customers":    "cleaned_customers.csv",
    "sellers":      "cleaned_sellers.csv",
    "geolocation":  "cleaned_geolocation.csv",
}

# Columns that should be parsed as datetime when reading CSV
# (pandas saves datetime as strings in CSV, so we must re-parse them)
DATETIME_COLS = {
    "orders": [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ],
    "order_items": ["shipping_limit_date"],
    "reviews": ["review_creation_date", "review_answer_timestamp"],
}

print("=" * 80)
print(" LOADING CLEANED DATA INTO SQL SERVER ".center(80, "="))
print("=" * 80)

for table_name, csv_file in TABLE_MAP.items():
    filepath = os.path.join(CLEAN_DIR, csv_file)
    start = time.time()

    # Read the CSV, parsing datetime columns if applicable
    parse_dates = DATETIME_COLS.get(table_name, None)
    df = pd.read_csv(filepath, parse_dates=parse_dates)

    print(f"\n  Loading {table_name:<15} ({df.shape[0]:>10,} rows x {df.shape[1]:>3} cols)...")

    # to_sql() parameters:
    #   name          → SQL table name
    #   con           → SQLAlchemy engine
    #   if_exists     → 'replace' drops and recreates the table each run
    #                   (use 'append' if you want to add to existing data)
    #   index         → False means don't write the pandas index as a column
    #   chunksize     → write N rows at a time to avoid memory overflow
    #                   1000 is a good balance between speed and memory
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists='replace',
        index=False,
        chunksize=1000
    )

    elapsed = time.time() - start
    print(f"  Done in {elapsed:.1f}s")

# ──────────────────────────────────────────────────────────────────────────────
# 4. VERIFY LOADED DATA
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(" VERIFICATION: ROW COUNTS IN SQL SERVER ".center(80, "="))
print("=" * 80)

with engine.connect() as conn:
    print(f"\n  {'Table':<20} {'SQL Rows':>12} {'CSV Rows':>12} {'Status':>10}")
    print(f"  {'─' * 55}")
    for table_name, csv_file in TABLE_MAP.items():
        # Count rows in SQL Server
        result = conn.execute(text(f"SELECT COUNT(*) FROM [{table_name}]"))
        sql_count = result.scalar()

        # Count rows using pandas (not line count) because some CSVs
        # contain embedded newlines in text fields (e.g. review comments)
        csv_path = os.path.join(CLEAN_DIR, csv_file)
        csv_count = len(pd.read_csv(csv_path, usecols=[0]))

        status = "OK" if sql_count == csv_count else "MISMATCH"
        print(f"  {table_name:<20} {sql_count:>12,} {csv_count:>12,} {status:>10}")

# ──────────────────────────────────────────────────────────────────────────────
# 5. SHOW TABLE SCHEMAS IN SQL SERVER
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(" TABLE SCHEMAS IN SQL SERVER ".center(80, "="))
print("=" * 80)

with engine.connect() as conn:
    for table_name in TABLE_MAP.keys():
        result = conn.execute(text(f"""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """))
        rows = result.fetchall()

        print(f"\n  {table_name.upper()}:")
        for col_name, data_type, max_len in rows:
            len_str = f"({max_len})" if max_len else ""
            print(f"    {col_name:<45} {data_type}{len_str}")

print("\n" + "=" * 80)
print(" DATA LOADING COMPLETE ".center(80, "="))
print("=" * 80)
print(f"\n  Database: {SERVER} / {DATABASE}")
print(f"  Tables loaded: {len(TABLE_MAP)}")
print("  Ready for Phase 2 SQL queries (sql_queries/ folder)\n")
