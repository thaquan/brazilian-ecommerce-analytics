/*
=============================================================================
 QUERY 4: RFM CUSTOMER SEGMENTATION
 Grain: one customer after aggregating delivered orders
 Frequency uses business thresholds because most Olist customers order once.
=============================================================================
*/

USE OlistEcommerce;
GO

SET NOCOUNT ON;

WITH analysis_reference AS (
    SELECT DATEADD(DAY, 1, CAST(MAX(order_purchase_timestamp) AS date)) AS analysis_date
    FROM dbo.Fact_Orders
    WHERE order_status = 'delivered'
),
rfm_raw AS (
    SELECT
        o.customer_unique_id,
        r.analysis_date,
        DATEDIFF(DAY, MAX(o.order_purchase_timestamp), r.analysis_date)
            AS recency_days,
        COUNT(*) AS frequency,
        SUM(o.total_payment) AS monetary
    FROM dbo.Fact_Orders o
    CROSS JOIN analysis_reference r
    WHERE o.order_status = 'delivered'
      AND o.total_payment IS NOT NULL
    GROUP BY o.customer_unique_id, r.analysis_date
),
rfm_percentiles AS (
    SELECT
        *,
        PERCENT_RANK() OVER (ORDER BY recency_days DESC) AS recency_percentile,
        PERCENT_RANK() OVER (ORDER BY monetary ASC) AS monetary_percentile
    FROM rfm_raw
),
rfm_scored AS (
    SELECT
        customer_unique_id,
        analysis_date,
        recency_days,
        frequency,
        monetary,
        CASE
            WHEN recency_percentile < 0.2 THEN 1
            WHEN recency_percentile < 0.4 THEN 2
            WHEN recency_percentile < 0.6 THEN 3
            WHEN recency_percentile < 0.8 THEN 4
            ELSE 5
        END AS r_score,
        CASE
            WHEN frequency = 1 THEN 1
            WHEN frequency = 2 THEN 3
            WHEN frequency = 3 THEN 4
            ELSE 5
        END AS f_score,
        CASE
            WHEN monetary_percentile < 0.2 THEN 1
            WHEN monetary_percentile < 0.4 THEN 2
            WHEN monetary_percentile < 0.6 THEN 3
            WHEN monetary_percentile < 0.8 THEN 4
            ELSE 5
        END AS m_score
    FROM rfm_percentiles
),
rfm_segmented AS (
    SELECT
        *,
        CONCAT(r_score, f_score, m_score) AS rfm_score,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4
                THEN 'Champions'
            WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3
                THEN 'At Risk'
            WHEN f_score >= 3 AND m_score >= 3
                THEN 'Loyal'
            WHEN r_score = 5 AND frequency = 1
                THEN 'New Customers'
            WHEN r_score >= 4 AND f_score <= 3
                THEN 'Potential Loyalists'
            WHEN r_score = 1 AND frequency = 1 AND m_score <= 2
                THEN 'Lost'
            WHEN r_score <= 2 AND f_score <= 2
                THEN 'Hibernating'
            ELSE 'Need Attention'
        END AS customer_segment
    FROM rfm_scored
)
SELECT
    customer_segment,
    COUNT(*) AS customer_count,
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS DECIMAL(6, 2))
        AS customer_share_pct,
    CAST(AVG(CAST(recency_days AS FLOAT)) AS DECIMAL(10, 2))
        AS avg_recency_days,
    CAST(AVG(CAST(frequency AS FLOAT)) AS DECIMAL(8, 2))
        AS avg_frequency,
    CAST(AVG(monetary) AS DECIMAL(18, 2)) AS avg_monetary_brl,
    CAST(SUM(monetary) AS DECIMAL(18, 2)) AS total_spend_brl,
    CAST(
        SUM(monetary) * 100.0 / SUM(SUM(monetary)) OVER ()
        AS DECIMAL(6, 2)
    ) AS spend_share_pct,
    MAX(analysis_date) AS analysis_date,
    CASE customer_segment
        WHEN 'Champions' THEN 'Reward, retain and cross-sell'
        WHEN 'At Risk' THEN 'Prioritized win-back campaign'
        WHEN 'Loyal' THEN 'Loyalty benefits and referrals'
        WHEN 'New Customers' THEN 'Onboarding and second-order incentive'
        WHEN 'Potential Loyalists' THEN 'Nurture toward repeat purchase'
        WHEN 'Lost' THEN 'Suppress costly campaigns or low-cost reactivation'
        WHEN 'Hibernating' THEN 'Low-cost re-engagement'
        ELSE 'Targeted offer based on recency and value'
    END AS recommended_action
FROM rfm_segmented
GROUP BY customer_segment
ORDER BY avg_monetary_brl DESC;
