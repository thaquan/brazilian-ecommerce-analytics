/*
=============================================================================
 QUERY 2: LOGISTICS PERFORMANCE & CUSTOMER SATISFACTION
 Grain: one delivered and reviewed order per row
 Interpretation: association, not proof of causality
=============================================================================
*/

USE OlistEcommerce;
GO

SET NOCOUNT ON;

WITH delivered_reviewed_orders AS (
    SELECT
        order_id,
        delivery_days,
        delivery_delay_days,
        is_late_delivery,
        review_score
    FROM dbo.Fact_Orders
    WHERE order_status = 'delivered'
      AND delivery_delay_days IS NOT NULL
      AND review_score IS NOT NULL
),
delivery_buckets AS (
    SELECT
        *,
        CASE
            WHEN delivery_delay_days <= 0 THEN 1
            WHEN delivery_delay_days <= 3 THEN 2
            WHEN delivery_delay_days <= 7 THEN 3
            WHEN delivery_delay_days <= 14 THEN 4
            ELSE 5
        END AS delay_bucket_sort,
        CASE
            WHEN delivery_delay_days <= 0 THEN 'On Time'
            WHEN delivery_delay_days <= 3 THEN '1-3 Days Late'
            WHEN delivery_delay_days <= 7 THEN '4-7 Days Late'
            WHEN delivery_delay_days <= 14 THEN '8-14 Days Late'
            ELSE '15+ Days Late'
        END AS delay_bucket
    FROM delivered_reviewed_orders
)
SELECT
    delay_bucket_sort,
    delay_bucket,
    COUNT(*) AS order_count,
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS DECIMAL(6, 2))
        AS order_share_pct,
    CAST(AVG(CAST(review_score AS FLOAT)) AS DECIMAL(5, 2))
        AS avg_review_score,
    CAST(
        SUM(CASE WHEN review_score >= 4 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
        AS DECIMAL(6, 2)
    ) AS positive_review_pct,
    CAST(
        SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
        AS DECIMAL(6, 2)
    ) AS negative_review_pct,
    CAST(AVG(delivery_days) AS DECIMAL(8, 2)) AS avg_delivery_days,
    CAST(AVG(delivery_delay_days) AS DECIMAL(8, 2)) AS avg_delay_days
FROM delivery_buckets
GROUP BY delay_bucket_sort, delay_bucket
ORDER BY delay_bucket_sort;
