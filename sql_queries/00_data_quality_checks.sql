/*
=============================================================================
 PHASE 2 DATA QUALITY GATES
 Fails immediately when corrected fact grains or reconciliations regress.
=============================================================================
*/

USE OlistEcommerce;
GO

SET NOCOUNT ON;

DECLARE @fact_orders_rows BIGINT = (SELECT COUNT_BIG(*) FROM dbo.Fact_Orders);
DECLARE @fact_orders_keys BIGINT = (
    SELECT COUNT_BIG(*) FROM (SELECT order_id FROM dbo.Fact_Orders GROUP BY order_id) d
);
DECLARE @fact_items_rows BIGINT = (SELECT COUNT_BIG(*) FROM dbo.Fact_Order_Items);
DECLARE @duplicate_item_keys BIGINT = (
    SELECT COUNT_BIG(*)
    FROM (
        SELECT order_id, order_item_id
        FROM dbo.Fact_Order_Items
        GROUP BY order_id, order_item_id
        HAVING COUNT_BIG(*) > 1
    ) d
);
DECLARE @orphan_items BIGINT = (
    SELECT COUNT_BIG(*)
    FROM dbo.Fact_Order_Items i
    LEFT JOIN dbo.Fact_Orders o ON i.order_id = o.order_id
    WHERE o.order_id IS NULL
);
DECLARE @invalid_unknown_delivery BIGINT = (
    SELECT COUNT_BIG(*)
    FROM dbo.Fact_Orders
    WHERE delivery_delay_days IS NULL
      AND is_late_delivery IS NOT NULL
);
DECLARE @total_gmv DECIMAL(18, 2) = (
    SELECT CAST(SUM(line_total) AS DECIMAL(18, 2))
    FROM dbo.Fact_Order_Items
);

IF @fact_orders_rows <> @fact_orders_keys
    THROW 51001, 'Fact_Orders contains duplicate order_id values.', 1;

IF @fact_orders_rows <> 99441
    THROW 51002, 'Fact_Orders row count differs from the Phase 1 baseline.', 1;

IF @fact_items_rows <> 112650
    THROW 51003, 'Fact_Order_Items row count differs from the Phase 1 baseline.', 1;

IF @duplicate_item_keys <> 0
    THROW 51004, 'Fact_Order_Items contains duplicate business keys.', 1;

IF @orphan_items <> 0
    THROW 51005, 'Fact_Order_Items contains orphan order IDs.', 1;

IF @invalid_unknown_delivery <> 0
    THROW 51006, 'Unknown deliveries have a non-null late-delivery flag.', 1;

IF ABS(@total_gmv - CAST(15843553.24 AS DECIMAL(18, 2))) > 0.01
    THROW 51007, 'Total GMV does not reconcile with cleaned order items.', 1;

SELECT
    @fact_orders_rows AS fact_orders_rows,
    @fact_items_rows AS fact_order_items_rows,
    @duplicate_item_keys AS duplicate_item_keys,
    @orphan_items AS orphan_order_items,
    @invalid_unknown_delivery AS invalid_unknown_delivery_rows,
    @total_gmv AS all_status_gmv_brl,
    CAST(SUM(CASE WHEN o.order_status = 'delivered' THEN i.line_total ELSE 0 END)
         AS DECIMAL(18, 2)) AS delivered_gmv_brl,
    SUM(CASE WHEN o.review_score IS NOT NULL THEN 1 ELSE 0 END)
        AS reviewed_orders,
    SUM(CASE WHEN o.delivery_delay_days IS NULL THEN 1 ELSE 0 END)
        AS unknown_delivery_orders
FROM dbo.Fact_Orders o
LEFT JOIN (
    SELECT order_id, SUM(line_total) AS line_total
    FROM dbo.Fact_Order_Items
    GROUP BY order_id
) i ON o.order_id = i.order_id;
