# 🔍 Tài Liệu Chi Tiết: SQL Business Analytics

## Tổng Quan

4 truy vấn SQL trong dự án này được thiết kế để trả lời 4 câu hỏi kinh doanh quan trọng nhất mà bất kỳ nền tảng E-Commerce nào cũng phải đối mặt. Mỗi truy vấn sử dụng kỹ thuật SQL nâng cao (Window Functions, CTEs, NTILE, CASE WHEN) — đây chính là những kỹ năng mà nhà tuyển dụng kiểm tra khi phỏng vấn vị trí Data Analyst.

```
Query 01: Khách hàng nào có giá trị cao nhất?
    ↓
Query 02: Giao hàng trễ ảnh hưởng đánh giá ra sao?
    ↓
Query 03: 20% sản phẩm nào mang lại 80% doanh thu?
    ↓
Query 04: Phân khúc 96K khách hàng thành 8 nhóm hành vi
```

---

## Query 1: Customer Value & Retention

### Câu hỏi kinh doanh
> "Khách hàng mua lại (Repeat) có giá trị hơn khách hàng mua 1 lần (One-time) bao nhiêu? Tỷ lệ khách quay lại là bao nhiêu?"

### Kỹ thuật SQL sử dụng

| Kỹ thuật | Mục đích |
|----------|----------|
| **CTE (Common Table Expression)** | Chia truy vấn phức tạp thành các bước logic nhỏ, dễ đọc |
| **COUNT(DISTINCT ...)** | Đếm số đơn hàng unique của mỗi khách (vì 1 đơn có thể có nhiều items) |
| **CASE WHEN** | Phân loại khách hàng thành "Repeat" hoặc "One-time" |
| **GROUP BY + HAVING** | Tổng hợp theo nhóm khách hàng |

### Luồng truy vấn

```sql
-- Bước 1: Đếm số đơn hàng của mỗi khách hàng
WITH customer_orders AS (
    SELECT 
        customer_unique_id,
        COUNT(DISTINCT order_id) AS order_count,
        SUM(line_total) AS total_spent
    FROM Fact_Order_Items
    GROUP BY customer_unique_id
),

-- Bước 2: Gắn nhãn Repeat vs One-time
customer_type AS (
    SELECT *,
        CASE 
            WHEN order_count > 1 THEN 'Repeat'
            ELSE 'One-time'
        END AS customer_type
    FROM customer_orders
)

-- Bước 3: So sánh giá trị trung bình giữa 2 nhóm
SELECT 
    customer_type,
    COUNT(*) AS customer_count,
    AVG(total_spent) AS avg_lifetime_value,
    AVG(order_count) AS avg_orders
FROM customer_type
GROUP BY customer_type;
```

### Tại sao dùng CTE thay vì Subquery?

> **CTE** giống như "đặt tên cho một bước trung gian". Thay vì viết một truy vấn dài ngoằn với subquery lồng nhau (khó đọc, khó debug), CTE chia thành các bước có tên rõ ràng:
> - `customer_orders` → "Tôi đang đếm đơn của từng khách"
> - `customer_type` → "Tôi đang phân loại khách"
> - SELECT cuối → "Tôi đang so sánh 2 nhóm"

### Kết quả quan trọng

| Nhóm | Số lượng | CLV trung bình | Đặc điểm |
|------|---------|----------------|----------|
| One-time | ~93,000 (97%) | Thấp | Mua 1 lần rồi biến mất |
| Repeat | ~3,000 (3%) | Cao gấp 2-3 lần | Khách hàng trung thành |

**Insight:** Chỉ 3% khách hàng quay lại → Olist có vấn đề nghiêm trọng về **Retention** (giữ chân khách).

---

## Query 2: Logistics Impact on Satisfaction

### Câu hỏi kinh doanh
> "Giao hàng trễ bao nhiêu ngày thì khách hàng bắt đầu 'phẫn nộ' (chấm điểm thấp)?"

### Kỹ thuật SQL sử dụng

| Kỹ thuật | Mục đích |
|----------|----------|
| **DATEDIFF()** | Tính số ngày chênh lệch giữa ngày giao thực tế và ngày giao dự kiến |
| **AVG() + GROUP BY** | Tính điểm đánh giá trung bình theo từng mức trễ |
| **CASE WHEN (bucketing)** | Gom các mức trễ thành các nhóm (tier) có ý nghĩa kinh doanh |
| **Window Function** | Tính tỷ lệ phần trăm đơn trễ tích lũy |

### Luồng truy vấn

```sql
-- Bước 1: Tính số ngày trễ/sớm cho mỗi đơn hàng
WITH delivery_analysis AS (
    SELECT
        order_id,
        delivery_delay_days,  -- Âm = sớm, Dương = trễ
        review_score,
        CASE
            WHEN delivery_delay_days <= -7  THEN 'Early 7+ days'
            WHEN delivery_delay_days <= 0   THEN 'On time'
            WHEN delivery_delay_days <= 3   THEN 'Late 1-3 days'
            WHEN delivery_delay_days <= 7   THEN 'Late 4-7 days'
            WHEN delivery_delay_days <= 14  THEN 'Late 8-14 days'
            ELSE                                 'Late 15+ days'
        END AS delay_tier
    FROM Fact_Order_Items
    WHERE delivery_delay_days IS NOT NULL
)

-- Bước 2: Tính trung bình review score theo từng mức trễ
SELECT
    delay_tier,
    COUNT(*) AS order_count,
    AVG(CAST(review_score AS FLOAT)) AS avg_review,
    -- Tỷ lệ đánh giá 1-2 sao ("Giận dữ")
    SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) * 100.0 
        / COUNT(*) AS pct_angry
FROM delivery_analysis
GROUP BY delay_tier
ORDER BY avg_review DESC;
```

### Tại sao dùng CASE WHEN bucketing?

> Nếu chỉ dùng `GROUP BY delivery_delay_days`, kết quả sẽ có 40+ dòng (từ -15 đến +25 ngày), rất khó đọc. **Bucketing** gom các giá trị liên tục thành các nhóm rời rạc có ý nghĩa kinh doanh:
> - "Late 1-3 days" = Hơi trễ, có thể chấp nhận
> - "Late 8-14 days" = Trễ nghiêm trọng, khách bắt đầu tức giận
> - "Late 15+ days" = Thảm họa dịch vụ

### Kết quả quan trọng

| Mức trễ | Điểm TB | % Giận dữ (1-2★) | Nhận xét |
|---------|---------|------------------|---------|
| Sớm 7+ ngày | ~4.5 | ~5% | Rất hài lòng |
| Đúng hạn | ~4.2 | ~8% | Hài lòng |
| Trễ 1-3 ngày | ~3.5 | ~25% | Bắt đầu khó chịu |
| Trễ 4-7 ngày | ~2.8 | ~45% | Khá tức giận |
| **Trễ 8-14 ngày** | **~2.0** | **~65%** | **"Ngưỡng phẫn nộ"** |
| Trễ 15+ ngày | ~1.5 | ~80% | Rất tức giận |

**Insight:** "Fury Threshold" (Ngưỡng phẫn nộ) là **8 ngày trễ**. Vượt qua mốc này, điểm đánh giá rơi xuống dưới 2.0 và tỷ lệ "giận dữ" tăng vọt lên 65%.

---

## Query 3: Pareto (80/20) Analysis

### Câu hỏi kinh doanh
> "20% sản phẩm/danh mục nào mang lại 80% tổng doanh thu? Đâu là 'Hero Products'?"

### Kỹ thuật SQL sử dụng

| Kỹ thuật | Mục đích |
|----------|----------|
| **Window Function: SUM() OVER()** | Tính doanh thu tích lũy (Cumulative Sum) mà không cần self-join |
| **Window Function: ROW_NUMBER()** | Xếp hạng sản phẩm theo doanh thu |
| **Subquery trong FROM** | Tính tổng doanh thu toàn bộ để làm mẫu số cho phần trăm |

### Luồng truy vấn

```sql
-- Bước 1: Tính doanh thu của từng danh mục
WITH category_revenue AS (
    SELECT
        p.category,
        SUM(f.line_total) AS revenue,
        COUNT(DISTINCT f.order_id) AS orders
    FROM Fact_Order_Items f
    JOIN Dim_Products p ON f.product_id = p.product_id
    GROUP BY p.category
),

-- Bước 2: Xếp hạng và tính % tích lũy
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rank,
        -- Cumulative Sum: Tổng tích lũy từ cao xuống thấp
        SUM(revenue) OVER (ORDER BY revenue DESC) AS cumulative_revenue,
        -- Tổng doanh thu toàn bộ
        SUM(revenue) OVER () AS total_revenue
    FROM category_revenue
)

-- Bước 3: Tính % tích lũy
SELECT *,
    cumulative_revenue * 100.0 / total_revenue AS cumulative_pct
FROM ranked
ORDER BY rank;
```

### Giải thích Window Function

```sql
SUM(revenue) OVER (ORDER BY revenue DESC)
```

> Hàm này tính **tổng tích lũy** (Running Total). Ví dụ:
>
> | Hạng | Danh mục | Doanh thu | Tích lũy | % Tích lũy |
> |------|---------|-----------|----------|------------|
> | 1 | health_beauty | $1.45M | $1.45M | 9.1% |
> | 2 | watches_gifts | $1.31M | $2.76M | 17.3% |
> | 3 | bed_bath_table | $1.26M | $4.02M | 25.2% |
> | ... | ... | ... | ... | ... |
> | 15 | ??? | $0.5M | **$12.7M** | **~80%** |
>
> → Đến hạng ~15 (tổng 74 danh mục), tổng tích lũy đạt ~80% → Đúng quy luật Pareto.

### Kết quả quan trọng

**Top 5 "Hero Categories":**
1. health_beauty (~$1.45M)
2. watches_gifts (~$1.31M)
3. bed_bath_table (~$1.26M)
4. sports_leisure (~$1.16M)
5. computers_accessories (~$1.07M)

**Insight:** ~20% danh mục (khoảng 15/74) tạo ra ~80% tổng doanh thu → Tập trung marketing vào nhóm này sẽ mang lại ROI cao nhất.

---

## Query 4: RFM Segmentation

### Câu hỏi kinh doanh
> "Làm thế nào để phân loại 96,000 khách hàng thành các nhóm hành vi khác nhau để có chiến lược marketing phù hợp?"

### RFM là gì?

| Chữ | Viết tắt của | Ý nghĩa | Cách tính |
|-----|-------------|---------|-----------|
| **R** | Recency | Gần đây | Số ngày kể từ lần mua cuối |
| **F** | Frequency | Tần suất | Số đơn hàng đã đặt |
| **M** | Monetary | Giá trị | Tổng tiền đã chi |

### Kỹ thuật SQL sử dụng

| Kỹ thuật | Mục đích |
|----------|----------|
| **DATEDIFF()** | Tính Recency (số ngày kể từ lần mua cuối) |
| **NTILE(5)** | Chia khách hàng thành 5 nhóm bằng nhau (quintile) cho mỗi chỉ số R, F, M |
| **CONCAT()** | Ghép 3 điểm R, F, M thành mã segment (ví dụ: "5-5-5") |
| **CASE WHEN (phức tạp)** | Ánh xạ mã RFM thành tên segment có ý nghĩa kinh doanh |

### Luồng truy vấn

```sql
-- Bước 1: Tính 3 chỉ số R, F, M cho mỗi khách hàng
WITH rfm_base AS (
    SELECT
        customer_unique_id,
        -- R: Số ngày từ lần mua cuối đến ngày phân tích
        DATEDIFF(DAY, MAX(order_purchase_timestamp), '2018-10-17') AS recency,
        -- F: Số đơn hàng unique
        COUNT(DISTINCT order_id) AS frequency,
        -- M: Tổng tiền đã chi
        SUM(line_total) AS monetary
    FROM Fact_Order_Items
    GROUP BY customer_unique_id
),

-- Bước 2: Chấm điểm 1-5 cho mỗi chỉ số bằng NTILE
rfm_scores AS (
    SELECT *,
        -- NTILE(5) chia 96K khách thành 5 nhóm bằng nhau
        -- Recency: Nhóm 5 = mua gần đây nhất (TỐT), Nhóm 1 = lâu nhất
        NTILE(5) OVER (ORDER BY recency DESC) AS r_score,
        -- Frequency: Nhóm 5 = mua nhiều nhất
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        -- Monetary: Nhóm 5 = chi nhiều nhất
        NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
    FROM rfm_base
),

-- Bước 3: Gán tên segment dựa trên tổ hợp R-F-M
rfm_segments AS (
    SELECT *,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 
                THEN 'Champions'
            WHEN r_score >= 3 AND f_score >= 3 
                THEN 'Loyal'
            WHEN r_score >= 4 AND f_score <= 2 
                THEN 'New Customers'
            WHEN r_score >= 3 AND f_score <= 2 AND m_score >= 3 
                THEN 'Potential Loyalist'
            WHEN r_score >= 3 AND f_score <= 2 AND m_score <= 2 
                THEN 'Promising'
            WHEN r_score <= 2 AND f_score >= 3 
                THEN 'At Risk'
            WHEN r_score <= 2 AND f_score <= 2 AND m_score >= 3 
                THEN 'Need Attention'
            ELSE 'Lost'
        END AS segment
    FROM rfm_scores
)

SELECT segment, COUNT(*) AS customers, AVG(monetary) AS avg_value
FROM rfm_segments
GROUP BY segment;
```

### Giải thích NTILE

```sql
NTILE(5) OVER (ORDER BY recency DESC) AS r_score
```

> **NTILE(5)** chia toàn bộ 96,000 khách hàng thành 5 nhóm **bằng nhau** (mỗi nhóm ~19,200 người), sắp xếp theo `recency` giảm dần.
>
> | Nhóm | Recency | Ý nghĩa |
> |------|---------|---------|
> | r_score = 5 | 0-60 ngày | Mua rất gần đây (Tốt nhất) |
> | r_score = 4 | 60-120 ngày | Khá gần |
> | r_score = 3 | 120-200 ngày | Trung bình |
> | r_score = 2 | 200-350 ngày | Khá lâu |
> | r_score = 1 | 350+ ngày | Rất lâu rồi (Tệ nhất) |

### 8 Phân Khúc Khách Hàng

| Segment | R | F | M | Chiến lược |
|---------|---|---|---|-----------|
| **Champions** | Cao | Cao | Cao | VIP Rewards, Early Access sản phẩm mới |
| **Loyal** | TB-Cao | Cao | TB-Cao | Chương trình loyalty, giảm giá độc quyền |
| **Potential Loyalist** | Cao | Thấp | TB | Nurture bằng email cá nhân hóa |
| **New Customers** | Rất cao | Rất thấp | Thấp | Onboarding flow, welcome voucher |
| **Promising** | Cao | Thấp | Thấp | Tăng giỏ hàng bằng bundle deals |
| **Need Attention** | TB | TB | TB | Re-engage bằng reminder email |
| **At Risk** | Thấp | Cao | TB-Cao | Win-back campaign khẩn cấp |
| **Lost** | Rất thấp | Thấp | Thấp | Last-resort: Flash sale hoặc bỏ qua |

---

## Tổng Kết Kỹ Thuật SQL

| Query | Kỹ thuật chính | Tại sao dùng |
|-------|---------------|-------------|
| 1 - Retention | CTE + CASE WHEN | Chia query phức tạp thành bước nhỏ |
| 2 - Logistics | CASE WHEN bucketing | Gom giá trị liên tục thành nhóm có ý nghĩa |
| 3 - Pareto | Window: SUM() OVER() | Tính tổng tích lũy không cần self-join |
| 4 - RFM | NTILE(5) | Phân nhóm đều, không bị bias bởi outlier |
