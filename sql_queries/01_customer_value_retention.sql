/*
=============================================================================
 QUERY 1: CUSTOMER VALUE & RETENTION
 Grain: one row per customer in the CTE; delivered orders only
 Monetary definition: customer spend from Fact_Orders.total_payment (BRL)
=============================================================================
*/

USE OlistEcommerce;
GO

SET NOCOUNT ON;

WITH customer_metrics AS (
    SELECT
        customer_unique_id,
        COUNT(*) AS total_orders,
        SUM(total_payment) AS total_spend,
        AVG(total_payment) AS average_order_value,
        MIN(order_purchase_timestamp) AS first_purchase,
        MAX(order_purchase_timestamp) AS last_purchase
    FROM dbo.Fact_Orders
    WHERE order_status = 'delivered'
      AND total_payment IS NOT NULL
    GROUP BY customer_unique_id
),
customer_segments AS (
    SELECT
        customer_unique_id,
        total_orders,
        total_spend,
        average_order_value,
        DATEDIFF(DAY, first_purchase, last_purchase) AS customer_lifespan_days,
        CASE
            WHEN total_orders >= 2 THEN 'Repeat Customer'
            ELSE 'One-Time Customer'
        END AS customer_segment
    FROM customer_metrics
)
SELECT
    customer_segment,
    COUNT(*) AS customer_count,
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS DECIMAL(6, 2))
        AS customer_share_pct,
    SUM(total_orders) AS total_orders,
    CAST(SUM(total_spend) AS DECIMAL(18, 2)) AS total_spend_brl,
    CAST(
        SUM(total_spend) * 100.0 / SUM(SUM(total_spend)) OVER ()
        AS DECIMAL(6, 2)
    ) AS spend_share_pct,
    CAST(AVG(total_spend) AS DECIMAL(18, 2)) AS avg_spend_per_customer_brl,
    CAST(AVG(average_order_value) AS DECIMAL(18, 2)) AS avg_order_value_brl,
    CAST(AVG(CAST(total_orders AS FLOAT)) AS DECIMAL(8, 2))
        AS avg_orders_per_customer,
    CAST(AVG(CAST(customer_lifespan_days AS FLOAT)) AS DECIMAL(10, 2))
        AS avg_customer_lifespan_days
FROM customer_segments
GROUP BY customer_segment
ORDER BY avg_spend_per_customer_brl DESC;
