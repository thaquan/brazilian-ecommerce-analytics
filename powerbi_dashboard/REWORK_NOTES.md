# Brazilian E-Commerce Dashboard — Rework

## Open the report

Open `final_dashboard_rework.pbip` in Power BI Desktop. The PBIP project keeps
the report definition and semantic model as source-controlled text files.

If Power BI displays **Some tables have incomplete or no data**, choose
**Refresh now**. The import model reads the existing local SQL Server source:
`localhost\SQLEXPRESS`, database `OlistEcommerce`.

## Delivered pages

1. **Executive Overview** — five KPI callouts, revenue vs prior year, top
   categories, delivery mix, monthly late rate, and operational health matrix.
2. **Product Analytics** — commercial KPIs, Pareto combo chart, price/freight
   scatter plot, and category performance matrix.
3. **Logistics** — fulfillment KPIs, state ranking with late-rate tooltips,
   delay-bucket combo chart, and monthly late-rate trend.
4. **Customer Insights** — customer KPIs, active/repeat trend, weekday matrix,
   top cities, and customer-type composition.

The Period, Category, and Status slicers are synchronized across all pages.

## Model improvements

- Corrected customer counting so it responds to fact/date filters.
- Added Active Customers, Repeat Customers, context-aware Repeat Rate, Revenue
  per Customer, product Pareto measures, Average Item Price, Average Freight,
  and a latest-complete-month MoM measure.
- Added ordered delivery-delay buckets and normalized Brazilian state location.
- Changed monetary formats from USD to BRL (`R$`).

## Design system

- 1280×720 light editorial layout.
- Accessible blue/orange/green/magenta palette with strong text contrast.
- Built-in Power BI visuals only; no external custom visual dependency.
- Azure Maps was tested but is disabled by the current tenant policy. The
  Logistics page therefore uses a deterministic ranked-state bar chart with
  Late Delivery Rate and Avg Review Score in tooltips.

## Validation

`powerbi-report-author validate` completes with **0 errors**. The remaining
warnings only indicate that external JSON-schema URLs were unreachable from
the sandbox during validation.

Final rendered previews are stored in the repository-level `images/` folder
and embedded in the main `README.md`.
