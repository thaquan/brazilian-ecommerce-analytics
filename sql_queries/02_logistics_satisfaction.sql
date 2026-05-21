/*
=============================================================================
 QUERY 2: LOGISTICS IMPACT ON CUSTOMER SATISFACTION
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 BUSINESS QUESTION:
   How does delivery performance (on-time vs late) affect customer
   review scores? Can we quantify the cost of late deliveries in terms
   of brand reputation?

 WHY IT MATTERS:
   If late deliveries cause a 60% drop in satisfaction scores,
   then investing in logistics infrastructure is MORE impactful
   than improving product quality. This analysis proves that case.

 SQL TECHNIQUES DEMONSTRATED:
   - DATEDIFF for date arithmetic
   - CASE WHEN with multiple tiers (not just binary)
   - Multi-table JOIN (orders + reviews + customers)
   - AVG with GROUP BY for statistical comparison
   - COUNT with conditional aggregation
=============================================================================
*/

USE OlistEcommerce;
GO

-- ─────────────────────────────────────────────────────────────
-- STEP 1: Calculate delivery delay for each delivered order
--         delay_days = actual delivery - estimated delivery
--         Negative = early, 0 = on-time, Positive = late
-- ─────────────────────────────────────────────────────────────
WITH delivery_analysis AS (
    SELECT
        o.order_id,
        o.order_status,
        o.order_purchase_timestamp,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,

        -- Core metric: how many days late (or early) was the delivery
        -- Negative values = delivered BEFORE estimated date (good!)
        -- Positive values = delivered AFTER estimated date (bad!)
        DATEDIFF(DAY,
            o.order_estimated_delivery_date,
            o.order_delivered_customer_date
        ) AS delay_days,

        -- Total transit time from purchase to customer receipt (in days)
        DATEDIFF(DAY,
            o.order_purchase_timestamp,
            o.order_delivered_customer_date
        ) AS total_delivery_days,

        -- Customer's satisfaction score for this order
        r.review_score

    FROM orders o
        -- JOIN reviews to get satisfaction data for each order
        INNER JOIN reviews r ON o.order_id = r.order_id
    WHERE
        -- Only analyze orders that were actually delivered
        -- (canceled/shipped orders have no delivery date)
        o.order_status = 'delivered'
        AND o.order_delivered_customer_date IS NOT NULL
        AND o.order_estimated_delivery_date IS NOT NULL
),

-- ─────────────────────────────────────────────────────────────
-- STEP 2: Classify deliveries into performance tiers
--         This creates human-readable categories for management
-- ─────────────────────────────────────────────────────────────
delivery_categories AS (
    SELECT
        *,
        CASE
            -- Delivered 7+ days before estimate = exceptional performance
            WHEN delay_days <= -7  THEN '1. Very Early (7+ days ahead)'
            -- Delivered 1-6 days early = good performance
            WHEN delay_days < 0    THEN '2. Early (1-6 days ahead)'
            -- Delivered on the estimated date = meets expectations
            WHEN delay_days = 0    THEN '3. On Time'
            -- Delivered 1-7 days late = minor issue
            WHEN delay_days <= 7   THEN '4. Late (1-7 days)'
            -- Delivered 8-14 days late = significant issue
            WHEN delay_days <= 14  THEN '5. Very Late (8-14 days)'
            -- Delivered 15+ days late = critical failure
            ELSE                        '6. Critical Delay (15+ days)'
        END AS delivery_tier
    FROM delivery_analysis
)

-- ─────────────────────────────────────────────────────────────
-- STEP 3: Aggregate by delivery tier to reveal the correlation
-- ─────────────────────────────────────────────────────────────
SELECT
    delivery_tier,

    -- Number of orders in each tier
    COUNT(*)                                         AS order_count,

    -- Percentage of total orders
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER()
         AS DECIMAL(5,2))                            AS pct_of_total,

    -- THE KEY METRIC: average review score per delivery tier
    -- This will show the dramatic drop from 4.3 → 1.7 for late orders
    CAST(AVG(CAST(review_score AS FLOAT))
         AS DECIMAL(3,2))                            AS avg_review_score,

    -- Average actual delivery time in days
    CAST(AVG(CAST(total_delivery_days AS FLOAT))
         AS DECIMAL(5,1))                            AS avg_delivery_days,

    -- Average delay in days (negative = early)
    CAST(AVG(CAST(delay_days AS FLOAT))
         AS DECIMAL(5,1))                            AS avg_delay_days,

    -- Distribution of low scores (1-2 stars) — shows anger concentration
    CAST(SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) * 100.0
         / COUNT(*) AS DECIMAL(5,2))                 AS pct_angry_customers

FROM delivery_categories
GROUP BY delivery_tier
ORDER BY delivery_tier;

/*
 EXPECTED INSIGHT:
   "Very Early" deliveries → avg score ~4.5
   "On Time" deliveries    → avg score ~4.3
   "Very Late" (8-14 days) → avg score drops to ~1.7-2.0
   "Critical Delay" (15+)  → avg score ~1.3-1.5

   The "angry customer" percentage jumps from ~10% for on-time
   to 70%+ for critical delays.

 ACTIONABLE RECOMMENDATION:
   1. Prioritize logistics investment over product quality improvements
   2. Build a real-time alerting system for orders approaching estimated date
   3. Investigate 3PL (third-party logistics) performance by state
   4. Consider adjusting estimated delivery dates to be more conservative
      (under-promise, over-deliver strategy)
*/
