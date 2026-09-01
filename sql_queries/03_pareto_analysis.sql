/*
=============================================================================
 QUERY 3: CATEGORY PARETO ANALYSIS
 Grain: delivered order items aggregated to product category
 Pareto metric: product revenue (freight reported separately)
=============================================================================
*/

USE OlistEcommerce;
GO

SET NOCOUNT ON;

WITH category_metrics AS (
    SELECT
        p.category,
        SUM(i.price) AS product_revenue,
        SUM(i.freight_value) AS freight_value,
        SUM(i.line_total) AS total_gmv,
        COUNT(*) AS units_sold,
        COUNT(DISTINCT i.order_id) AS order_count,
        COUNT(DISTINCT i.product_id) AS unique_products
    FROM dbo.Fact_Order_Items i
    INNER JOIN dbo.Fact_Orders o
        ON i.order_id = o.order_id
    INNER JOIN dbo.Dim_Products p
        ON i.product_id = p.product_id
    WHERE o.order_status = 'delivered'
    GROUP BY p.category
),
category_ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY product_revenue DESC, category ASC
        ) AS revenue_rank,
        COUNT(*) OVER () AS total_categories,
        SUM(product_revenue) OVER () AS total_product_revenue,
        SUM(product_revenue) OVER (
            ORDER BY product_revenue DESC, category ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue
    FROM category_metrics
)
SELECT
    revenue_rank,
    category,
    CAST(product_revenue AS DECIMAL(18, 2)) AS product_revenue_brl,
    CAST(freight_value AS DECIMAL(18, 2)) AS freight_value_brl,
    CAST(total_gmv AS DECIMAL(18, 2)) AS total_gmv_brl,
    order_count,
    units_sold,
    unique_products,
    CAST(product_revenue * 100.0 / total_product_revenue AS DECIMAL(7, 3))
        AS revenue_share_pct,
    CAST(cumulative_revenue AS DECIMAL(18, 2)) AS cumulative_revenue_brl,
    CAST(cumulative_revenue * 100.0 / total_product_revenue AS DECIMAL(7, 3))
        AS cumulative_revenue_pct,
    CAST(revenue_rank * 100.0 / total_categories AS DECIMAL(7, 3))
        AS categories_included_pct,
    CASE
        WHEN cumulative_revenue - product_revenue < total_product_revenue * 0.8
            THEN 'Vital Few'
        ELSE 'Long Tail'
    END AS pareto_group
FROM category_ranked
ORDER BY revenue_rank;
