/*
=============================================================================
 QUERY 3: PARETO ANALYSIS (80/20 RULE) — PRODUCT CATEGORY REVENUE
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 BUSINESS QUESTION:
   Which product categories drive the majority of revenue?
   Does the Pareto principle (80/20 rule) apply to Olist's business?

 WHY IT MATTERS:
   If 20% of categories generate 80% of revenue, the business should
   concentrate inventory, marketing, and supplier management on those
   categories. Spreading resources evenly across all 73 categories
   is wasteful and suboptimal.

 SQL TECHNIQUES DEMONSTRATED:
   - SUM() OVER(ORDER BY ...) for cumulative (running) totals
   - SUM() OVER() for grand total calculation (no partition = entire result)
   - DENSE_RANK() for identifying hero products within categories
   - Subquery + CTE layering for multi-step analysis
=============================================================================
*/

USE OlistEcommerce;
GO

-- ─────────────────────────────────────────────────────────────
-- PART A: PARETO ANALYSIS BY PRODUCT CATEGORY
-- ─────────────────────────────────────────────────────────────

-- STEP 1: Calculate total revenue per category
WITH category_revenue AS (
    SELECT
        p.product_category_name_english       AS category,
        -- Revenue = sum of product prices + freight values
        -- This matches the GMV (Gross Merchandise Value) definition
        CAST(SUM(oi.price + oi.freight_value)
             AS DECIMAL(15,2))                AS revenue,
        -- Also track order volume for context
        COUNT(DISTINCT oi.order_id)           AS order_count,
        -- Number of unique products sold in this category
        COUNT(DISTINCT oi.product_id)         AS unique_products
    FROM order_items oi
        INNER JOIN products p  ON oi.product_id = p.product_id
        INNER JOIN orders o    ON oi.order_id   = o.order_id
    WHERE
        o.order_status = 'delivered'
    GROUP BY
        p.product_category_name_english
),

-- STEP 2: Calculate cumulative revenue and percentages
-- This is where the Pareto magic happens — we see how revenue
-- accumulates as we add categories from highest to lowest
category_pareto AS (
    SELECT
        category,
        revenue,
        order_count,
        unique_products,

        -- Running cumulative revenue, ordered from highest to lowest
        -- SUM OVER ORDER BY creates a "running total" window
        SUM(revenue) OVER (ORDER BY revenue DESC)   AS cumulative_revenue,

        -- Grand total revenue (no ORDER BY = sum of ALL rows)
        SUM(revenue) OVER ()                         AS grand_total,

        -- Rank categories by revenue (DENSE_RANK = no gaps in ranking)
        DENSE_RANK() OVER (ORDER BY revenue DESC)    AS revenue_rank,

        -- Total number of categories
        COUNT(*) OVER ()                             AS total_categories
    FROM category_revenue
)

-- STEP 3: Final output with Pareto percentages
SELECT
    revenue_rank,
    category,
    revenue,
    order_count,
    unique_products,

    -- What % of total revenue does this single category contribute?
    CAST(revenue * 100.0 / grand_total
         AS DECIMAL(5,2))                            AS pct_of_revenue,

    -- What % of total revenue is covered UP TO and INCLUDING this category?
    -- When this reaches 80%, we've found the "vital few" (Pareto principle)
    CAST(cumulative_revenue * 100.0 / grand_total
         AS DECIMAL(5,2))                            AS cumulative_pct,

    -- What % of categories have we included so far?
    CAST(revenue_rank * 100.0 / total_categories
         AS DECIMAL(5,2))                            AS pct_of_categories,

    -- Flag: is this category part of the "vital 80%" ?
    CASE
        WHEN (SUM(revenue) OVER (ORDER BY revenue DESC
              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING))
             < grand_total * 0.8
             OR revenue_rank = 1
        THEN 'TOP 80%'
        ELSE 'LONG TAIL'
    END                                              AS pareto_group

FROM category_pareto
ORDER BY revenue_rank;

/*
 ─────────────────────────────────────────────────────────────
 PART B: HERO PRODUCTS — TOP 15 INDIVIDUAL PRODUCTS BY REVENUE
 ─────────────────────────────────────────────────────────────
 After identifying the top CATEGORIES, drill down to find the
 specific products that are the biggest revenue generators.
 These "hero products" must NEVER go out of stock.
*/

;WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_category_name_english            AS category,
        CAST(SUM(oi.price + oi.freight_value)
             AS DECIMAL(15,2))                     AS revenue,
        COUNT(*)                                   AS units_sold,
        CAST(AVG(CAST(r.review_score AS FLOAT))
             AS DECIMAL(3,2))                      AS avg_review_score,
        -- Rank this product within its category
        DENSE_RANK() OVER (
            PARTITION BY p.product_category_name_english
            ORDER BY SUM(oi.price + oi.freight_value) DESC
        )                                          AS rank_in_category
    FROM order_items oi
        INNER JOIN products p  ON oi.product_id = p.product_id
        INNER JOIN orders o    ON oi.order_id   = o.order_id
        LEFT JOIN reviews r    ON o.order_id    = r.order_id
    WHERE
        o.order_status = 'delivered'
    GROUP BY
        p.product_id,
        p.product_category_name_english
)

-- Show the top 15 revenue-generating products across all categories
SELECT TOP 15
    product_id,
    category,
    revenue,
    units_sold,
    avg_review_score,
    rank_in_category
FROM product_revenue
ORDER BY revenue DESC;

/*
 EXPECTED INSIGHT:
   The top 3 categories (Health/Beauty, Watches/Gifts, Bed/Bath/Table)
   contribute over $3.9M — dominating total platform revenue.
   Approximately 20% of categories generate ~80% of revenue,
   confirming the Pareto principle.

 ACTIONABLE RECOMMENDATION:
   1. Set up emergency safety stock for the top 15 hero products
   2. Allocate 80% of ad spend to the top 20% of categories
   3. Consider delisting or reducing inventory for long-tail categories
      with minimal revenue contribution
*/
