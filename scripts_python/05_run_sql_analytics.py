"""
Run and validate all Phase 2 SQL analytics with the same ODBC connection used
by the data pipeline. This avoids relying on the separately installed sqlcmd
client and prints compact JSON results for review.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pyodbc


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql_queries"

SERVER = os.getenv("OLIST_SQL_SERVER", r"localhost\SQLEXPRESS")
DATABASE = os.getenv("OLIST_SQL_DATABASE", "OlistEcommerce")
DRIVER = os.getenv("OLIST_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

SQL_FILES = [
    "00_data_quality_checks.sql",
    "01_customer_value_retention.sql",
    "02_logistics_satisfaction.sql",
    "03_pareto_analysis.sql",
    "04_rfm_segmentation.sql",
]


def split_batches(sql_text: str) -> list[str]:
    """Split a SQL Server script on standalone GO batch separators."""
    return [
        batch.strip()
        for batch in re.split(r"^\s*GO\s*$", sql_text, flags=re.MULTILINE | re.IGNORECASE)
        if batch.strip()
    ]


def run_script(cursor: pyodbc.Cursor, path: Path) -> list[dict[str, Any]]:
    """Execute every batch and return the final tabular result set."""
    final_rows: list[dict[str, Any]] = []

    for batch in split_batches(path.read_text(encoding="utf-8")):
        cursor.execute(batch)

        while True:
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                final_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            if not cursor.nextset():
                break

    return final_rows


def as_float(value: Any) -> float:
    return float(value or 0)


def validate_results(results: dict[str, list[dict[str, Any]]]) -> None:
    quality = results["00_data_quality_checks.sql"][0]
    assert quality["fact_orders_rows"] == 99441
    assert quality["fact_order_items_rows"] == 112650
    assert quality["duplicate_item_keys"] == 0
    assert quality["orphan_order_items"] == 0
    assert quality["invalid_unknown_delivery_rows"] == 0
    assert abs(as_float(quality["all_status_gmv_brl"]) - 15843553.24) <= 0.01

    customer = results["01_customer_value_retention.sql"]
    assert {row["customer_segment"] for row in customer} == {
        "One-Time Customer", "Repeat Customer"
    }
    assert abs(sum(as_float(row["customer_share_pct"]) for row in customer) - 100) <= 0.02
    assert abs(sum(as_float(row["spend_share_pct"]) for row in customer) - 100) <= 0.02

    logistics = results["02_logistics_satisfaction.sql"]
    assert len(logistics) == 5
    assert [row["delay_bucket_sort"] for row in logistics] == [1, 2, 3, 4, 5]
    assert abs(sum(as_float(row["order_share_pct"]) for row in logistics) - 100) <= 0.05

    pareto = results["03_pareto_analysis.sql"]
    assert len(pareto) == 74
    assert [row["revenue_rank"] for row in pareto] == list(range(1, 75))
    assert abs(as_float(pareto[-1]["cumulative_revenue_pct"]) - 100) <= 0.001
    assert abs(sum(as_float(row["revenue_share_pct"]) for row in pareto) - 100) <= 0.05

    rfm = results["04_rfm_segmentation.sql"]
    expected_segments = {
        "Champions", "At Risk", "Loyal", "New Customers",
        "Potential Loyalists", "Lost", "Hibernating", "Need Attention"
    }
    assert {row["customer_segment"] for row in rfm} == expected_segments
    assert abs(sum(as_float(row["customer_share_pct"]) for row in rfm) - 100) <= 0.05
    assert abs(sum(as_float(row["spend_share_pct"]) for row in rfm) - 100) <= 0.05


def main() -> None:
    connection_string = (
        f"DRIVER={{{DRIVER}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
        "Encrypt=no"
    )

    results: dict[str, list[dict[str, Any]]] = {}
    with pyodbc.connect(connection_string, autocommit=True) as connection:
        cursor = connection.cursor()
        for filename in SQL_FILES:
            rows = run_script(cursor, SQL_DIR / filename)
            if not rows:
                raise AssertionError(f"{filename} returned no result rows")
            results[filename] = rows

    validate_results(results)

    for filename, rows in results.items():
        print(f"\n=== {filename} ({len(rows)} rows) ===")
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))

    print("\nAll Phase 2 SQL validation checks passed.")


if __name__ == "__main__":
    main()
