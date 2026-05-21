/*
=============================================================================
 QUERY 4: RFM CUSTOMER SEGMENTATION
 Brazilian E-Commerce (Olist) — Portfolio Project
=============================================================================
 BUSINESS QUESTION:
   How can we segment all customers into actionable groups based on
   their purchasing behavior? Who are our Champions, who is At Risk,
   and who has already Churned?

 WHY IT MATTERS:
   RFM (Recency, Frequency, Monetary) is the gold standard for
   customer segmentation in retail. It transforms raw transaction data
   into marketing-ready segments that drive personalized campaigns.

 THE THREE DIMENSIONS:
   R (Recency)   = Days since last purchase → lower = better
   F (Frequency) = Total number of orders   → higher = better
   M (Monetary)  = Total spend amount       → higher = better

 SQL TECHNIQUES DEMONSTRATED:
   - Multiple layered CTEs (4 levels deep)
   - NTILE() window function for percentile-based scoring
   - DATEDIFF with subquery for reference date
   - CONCAT for composite score creation
   - CASE WHEN with pattern matching for segment labeling
=============================================================================
*/

USE OlistEcommerce;
GO

-- ─────────────────────────────────────────────────────────────
-- STEP 1: Calculate raw RFM values for each customer
-- ─────────────────────────────────────────────────────────────
-- Use the maximum order date in the dataset as the "analysis date"
-- (since this is historical data, we can't use GETDATE())

WITH rfm_raw AS (
    SELECT
        c.customer_unique_id,

        -- RECENCY: Days since last purchase
        -- Lower recency = more recent = more engaged
        DATEDIFF(DAY,
            MAX(o.order_purchase_timestamp),
            -- Reference date = the latest order in the entire dataset
            (SELECT MAX(order_purchase_timestamp) FROM orders)
        ) AS recency_days,

        -- FREQUENCY: Number of distinct orders
        -- Higher frequency = more loyal customer
        COUNT(DISTINCT o.order_id)        AS frequency,

        -- MONETARY: Total amount spent across all orders
        -- Higher monetary = more valuable customer
        CAST(SUM(p.payment_value)
             AS DECIMAL(12,2))            AS monetary

    FROM orders o
        INNER JOIN customers c ON o.customer_id = c.customer_id
        INNER JOIN payments p  ON o.order_id    = p.order_id
    WHERE
        o.order_status = 'delivered'
    GROUP BY
        c.customer_unique_id
),

-- ─────────────────────────────────────────────────────────────
-- STEP 2: Score each dimension on a 1-5 scale using NTILE
-- ─────────────────────────────────────────────────────────────
-- NTILE(5) divides the ordered dataset into 5 equal groups (quintiles)
-- For Recency: score 5 = most recent (best), score 1 = least recent
-- For Frequency & Monetary: score 5 = highest (best), score 1 = lowest

rfm_scored AS (
    SELECT
        customer_unique_id,
        recency_days,
        frequency,
        monetary,

        -- Recency score: ORDER BY ASC because LOWER recency = BETTER
        -- NTILE(5) assigns 1 to the lowest quintile, 5 to the highest
        -- But we want 5 = most recent, so ORDER BY recency_days ASC
        -- gives 1 to lowest recency (=most recent) → we need to REVERSE
        -- Solution: 6 - NTILE gives us 5 for most recent, 1 for oldest
        (6 - NTILE(5) OVER (ORDER BY recency_days ASC)) AS r_score,

        -- Frequency score: ORDER BY ASC, NTILE naturally gives
        -- higher scores to higher frequency values
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,

        -- Monetary score: same logic as frequency
        NTILE(5) OVER (ORDER BY monetary ASC)  AS m_score

    FROM rfm_raw
),

-- ─────────────────────────────────────────────────────────────
-- STEP 3: Create composite RFM score and assign segment labels
-- ─────────────────────────────────────────────────────────────
rfm_segments AS (
    SELECT
        customer_unique_id,
        recency_days,
        frequency,
        monetary,
        r_score,
        f_score,
        m_score,

        -- Composite score as a string (e.g., "555" = Champion)
        CONCAT(r_score, f_score, m_score) AS rfm_score,

        -- Combined numeric score for quick sorting (sum of all 3)
        (r_score + f_score + m_score)     AS rfm_total,

        -- Assign human-readable segment labels based on score patterns
        -- These labels are industry-standard RFM segment names
        CASE
            -- Champions: Recent, frequent, high-value buyers (best customers)
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4
                THEN 'Champions'

            -- Loyal Customers: Frequent buyers, may not be most recent
            WHEN f_score >= 4 AND m_score >= 3
                THEN 'Loyal Customers'

            -- Potential Loyalists: Recent buyers with moderate frequency
            WHEN r_score >= 4 AND f_score >= 2 AND f_score <= 4
                THEN 'Potential Loyalists'

            -- New Customers: Very recent but low frequency
            WHEN r_score >= 4 AND f_score <= 2
                THEN 'New Customers'

            -- Promising: Recent, low frequency, low monetary
            WHEN r_score >= 3 AND f_score <= 2 AND m_score <= 2
                THEN 'Promising'

            -- Need Attention: Above average across all dimensions but slipping
            WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3
                THEN 'Need Attention'

            -- About to Sleep: Below average recency, moderate F&M
            WHEN r_score >= 2 AND r_score <= 3 AND f_score >= 2
                THEN 'About to Sleep'

            -- At Risk: Used to be good customers, now inactive
            WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3
                THEN 'At Risk'

            -- Cannot Lose Them: Historically highest value but going dormant
            WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4
                THEN 'Cannot Lose Them'

            -- Hibernating: Low recency, low frequency
            WHEN r_score <= 2 AND f_score <= 2
                THEN 'Hibernating'

            -- Lost: Lowest scores across all dimensions
            WHEN r_score = 1 AND f_score = 1 AND m_score = 1
                THEN 'Lost'

            ELSE 'Other'
        END AS customer_segment
    FROM rfm_scored
)

-- ─────────────────────────────────────────────────────────────
-- STEP 4: Aggregate results by segment for executive reporting
-- ─────────────────────────────────────────────────────────────
SELECT
    customer_segment,

    -- Number of customers in this segment
    COUNT(*)                                         AS customer_count,

    -- Percentage of total customer base
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER()
         AS DECIMAL(5,2))                            AS pct_of_total,

    -- Average recency in days (how recently they purchased)
    CAST(AVG(CAST(recency_days AS FLOAT))
         AS DECIMAL(7,1))                            AS avg_recency_days,

    -- Average number of orders
    CAST(AVG(CAST(frequency AS FLOAT))
         AS DECIMAL(5,2))                            AS avg_frequency,

    -- Average total spend
    CAST(AVG(monetary) AS DECIMAL(10,2))             AS avg_monetary,

    -- Total revenue contribution from this segment
    CAST(SUM(monetary) AS DECIMAL(15,2))             AS total_revenue,

    -- Revenue share of this segment
    CAST(SUM(monetary) * 100.0
         / SUM(SUM(monetary)) OVER()
         AS DECIMAL(5,2))                            AS revenue_share_pct

FROM rfm_segments
GROUP BY customer_segment
ORDER BY avg_monetary DESC;

/*
 EXPECTED INSIGHT:
   - "Champions" (score 555): ~1-3% of customers but highest avg spend
   - "Hibernating" / "Lost": Largest group (~40-50%), minimal recent activity
   - "At Risk" / "Cannot Lose Them": High-value but declining engagement

   Note: Because Olist has very low repeat purchase rates (~3%),
   most customers will cluster in "New Customers" or "Hibernating"
   segments. This itself is a critical finding.

 ACTIONABLE RECOMMENDATION:
   1. Champions → Exclusive loyalty program, early access to deals
   2. At Risk → Urgent win-back campaign with personalized discounts
   3. Cannot Lose Them → VIP outreach, personal account manager
   4. New Customers → Onboarding email sequence, first-repeat incentive
   5. Hibernating → Low-cost reactivation (push notification, email)
   6. Lost → Remove from active campaigns to save marketing budget
*/
