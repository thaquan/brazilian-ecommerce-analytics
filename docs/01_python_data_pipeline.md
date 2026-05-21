# 🐍 Tài Liệu Chi Tiết: Python Data Pipeline

## Tổng Quan Luồng Hoạt Động

```
Raw CSV (8 files)
      │
      ▼
┌─────────────────────┐
│ 01_load_and_profile  │  ← Khám phá dữ liệu (Đọc, KHÔNG sửa)
│   "Chụp X-quang"    │
└─────────┬───────────┘
          │  Báo cáo profiling (console)
          ▼
┌─────────────────────┐
│ 02_data_cleaning     │  ← Làm sạch (5 bước có hệ thống)
│   "Phẫu thuật"      │
└─────────┬───────────┘
          │  8 cleaned CSVs → /data/cleaned/
          ▼
┌─────────────────────┐
│ 03_load_to_sqlserver │  ← Nạp vào SQL Server Express
│   "Nhập kho"        │
└─────────┬───────────┘
          │  8 tables trong DB OlistEcommerce
          ▼
┌─────────────────────┐
│ 04_star_schema_builder│  ← Xây Star Schema (1 Fact + 4 Dims)
│   "Kiến trúc sư"     │
└─────────┬────────────┘
          │  5 CSVs → /data/star_schema/
          │  5 tables → SQL Server
          ▼
     Power BI Desktop
```

---

## Script 1: `01_load_and_profile.py`

### Mục đích
Đây là bước **"Chụp X-quang"** — đọc toàn bộ 8 file CSV gốc và in ra báo cáo chất lượng dữ liệu. Script này **KHÔNG sửa đổi** bất kỳ dữ liệu nào, chỉ đọc và báo cáo.

### Tại sao phải làm bước này?
> Trước khi viết BẤT KỲ dòng code xử lý nào, một Data Analyst chuyên nghiệp phải hiểu "tính cách" của dữ liệu — hình dạng, điểm bất thường, và các lỗ hổng. Bỏ qua bước này giống như phẫu thuật mà không đọc phim X-quang.

### Các hàm và kỹ thuật chính

| Kỹ thuật | Code | Mục đích |
|----------|------|----------|
| **Đường dẫn động** | `os.path.abspath(__file__)` | Đảm bảo script chạy đúng dù người dùng ở thư mục nào |
| **Dictionary mapping** | `FILE_MAP = {"customers": "olist_customers_dataset.csv", ...}` | Ánh xạ tên ngắn → tên file thật, tiện cho vòng lặp |
| **Vòng lặp load** | `for name, file in FILE_MAP.items(): pd.read_csv(...)` | Load 8 bảng trong 1 vòng lặp thay vì 8 dòng code riêng |
| **Profiling tự động** | `df.dtypes`, `df.isnull().sum()`, `df.nunique()` | Kiểm tra kiểu dữ liệu, số lượng missing, số giá trị unique |
| **Phát hiện cột datetime** | Kiểm tra tên cột chứa "timestamp" hoặc "date" | Xác định các cột cần chuyển đổi sang datetime |

### Kết quả đầu ra (Console)
- Số dòng × số cột của mỗi bảng
- Danh sách cột có missing values (và tỷ lệ %)
- Kiểu dữ liệu hiện tại vs kiểu dữ liệu mong muốn
- Các giá trị mẫu (sample) để kiểm tra bằng mắt

### Phát hiện quan trọng từ Profiling

| Bảng | Phát hiện | Ý nghĩa |
|------|-----------|---------|
| `orders` | 5 cột timestamp nhưng kiểu `object` | Cần chuyển sang `datetime64` |
| `orders` | `order_delivered_customer_date` có ~2,965 NaN | MNAR — đơn hàng chưa giao xong, KHÔNG phải lỗi |
| `products` | `product_category_name` có 610 NaN | Sản phẩm chưa được phân loại |
| `order_reviews` | `review_comment_message` có ~58,247 NaN | Khách không viết comment (bình thường) |
| `geolocation` | 1,000,163 dòng nhưng chỉ ~19K zip codes unique | Nhiều bản ghi trùng lặp |

---

## Script 2: `02_data_cleaning.py`

### Mục đích
Đây là bước **"Phẫu thuật"** — áp dụng 5 bước làm sạch có hệ thống, biến dữ liệu thô thành dữ liệu sẵn sàng cho phân tích.

### Pipeline 5 bước

```
Bước 1: Chuyển đổi kiểu dữ liệu (Datetime Casting)
    ↓
Bước 2: Xử lý Missing Values (Chiến lược MNAR)
    ↓
Bước 3: Dịch danh mục sản phẩm (PT → EN)
    ↓
Bước 4: Phát hiện & gắn cờ Outlier (Phương pháp IQR)
    ↓
Bước 5: Export CSV đã làm sạch
```

### Bước 1: Chuyển đổi Datetime

```python
DATETIME_COLS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
    "order_items": ["shipping_limit_date"]
}

# errors='coerce' → Nếu giá trị không parse được thì trả về NaT thay vì crash
pd.to_datetime(df[col], errors='coerce')
```

**Tại sao dùng `errors='coerce'`?**
> Dữ liệu thực tế có thể chứa giá trị bất thường (ví dụ: "N/A", "0000-00-00"). Thay vì để script crash, `coerce` sẽ chuyển chúng thành `NaT` (Not a Time) — tương đương NULL cho datetime. Điều này an toàn hơn cho pipeline production.

### Bước 2: Xử lý Missing Values (Chiến lược MNAR)

**MNAR = Missing Not At Random** — Dữ liệu thiếu có LÝ DO kinh doanh, không phải lỗi kỹ thuật.

| Cột | Chiến lược | Lý do |
|-----|-----------|-------|
| `order_delivered_customer_date` = NaT | **GIỮ NGUYÊN NaT** | Đơn hàng đang vận chuyển hoặc bị hủy → thiếu ngày giao là đúng logic |
| `order_approved_at` = NaT | **GIỮ NGUYÊN NaT** | Đơn hàng chưa được duyệt thanh toán |
| `product_category_name` = NaN | **Điền "unknown"** | Sản phẩm chưa phân loại, cần giá trị mặc định để tránh lỗi JOIN |
| `review_comment_message` = NaN | **GIỮ NGUYÊN NaN** | Khách không viết nhận xét (bình thường, không phải lỗi) |

**Tại sao KHÔNG dùng `fillna(mean)` hay `fillna(0)` cho cột datetime?**
> Nếu điền một ngày giả (ví dụ: ngày trung bình) cho đơn hàng chưa giao, thì khi tính `delivery_days` sẽ ra kết quả sai hoàn toàn — hệ thống sẽ nghĩ rằng đơn hàng đã giao thành công với thời gian giao X ngày, trong khi thực tế nó chưa bao giờ được giao.

### Bước 3: Dịch Danh Mục Sản Phẩm (PT → EN)

```python
# Dùng bảng dịch có sẵn từ Kaggle
translation = pd.read_csv("product_category_name_translation.csv")

# Merge (LEFT JOIN) để giữ lại tất cả sản phẩm, kể cả những sản phẩm
# không có bản dịch trong bảng translation
products = products.merge(translation, on="product_category_name", how="left")

# 3 danh mục bị thiếu trong bảng dịch → bổ sung thủ công
MANUAL_TRANSLATIONS = {
    "pc_gamer":             "computers",
    "portateis_cozinha_e_preparadores_de_alimentos": "small_kitchen_appliances",
    "relogios_presentes":   "watches_gifts"  # Đã có nhưng bị miss do encoding
}
```

**Tại sao dùng LEFT JOIN chứ không phải INNER JOIN?**
> INNER JOIN sẽ loại bỏ những sản phẩm không có bản dịch. LEFT JOIN giữ lại TẤT CẢ sản phẩm, những sản phẩm thiếu bản dịch sẽ có giá trị NaN — sau đó ta xử lý riêng bằng `MANUAL_TRANSLATIONS`.

### Bước 4: Phát Hiện & Gắn Cờ Outlier (IQR)

```python
def flag_outliers_iqr(df, column, new_flag_col):
    """
    Phương pháp IQR (Interquartile Range):
    - Q1 = Phân vị 25%
    - Q3 = Phân vị 75%
    - IQR = Q3 - Q1
    - Outlier = giá trị < Q1 - 1.5*IQR hoặc > Q3 + 1.5*IQR
    
    KHÔNG XÓA outlier, chỉ GẮN CỜ (0 hoặc 1)
    """
    Q1 = df[column].quantile(0.25)
    Q3 = df[column].quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    df[new_flag_col] = ((df[column] < lower) | (df[column] > upper)).astype(int)
    return df
```

**Tại sao GẮN CỜ thay vì XÓA outlier?**
> Một sản phẩm có giá R$6,735 (cao bất thường) vẫn là giao dịch hợp lệ. Xóa nó sẽ khiến tổng doanh thu (GMV) bị thiếu ~0.5%. Bằng cách gắn cờ `is_outlier_price = 1`, analyst có thể TÙY CHỌN lọc bỏ hoặc giữ lại tùy theo bài toán cụ thể.

### Bước 5: Export & Xác Minh

```python
# Export từng bảng đã clean
for name, df in cleaned_tables.items():
    output_path = os.path.join(CLEAN_DIR, f"{name}_cleaned.csv")
    df.to_csv(output_path, index=False)

# Xác minh: Đọc lại file CSV vừa export và so sánh số dòng
for name, df in cleaned_tables.items():
    reloaded = pd.read_csv(output_path)
    assert len(reloaded) == len(df), f"Row count mismatch for {name}!"
```

---

## Script 3: `03_load_to_sqlserver.py`

### Mục đích
Nạp 8 file CSV đã làm sạch vào SQL Server Express để phục vụ cho phân tích SQL và Power BI DirectQuery.

### Kỹ thuật kết nối

```python
from sqlalchemy import create_engine

# Connection string sử dụng Windows Authentication (không cần password)
# TrustServerCertificate=yes → Bỏ qua lỗi SSL certificate (môi trường local)
engine = create_engine(
    "mssql+pyodbc://localhost\\SQLEXPRESS/OlistEcommerce"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Trusted_Connection=yes"
    "&TrustServerCertificate=yes"
)
```

### Xử lý đặc biệt: Đếm dòng CSV có chứa ký tự xuống dòng

```python
# Vấn đề: Cột review_comment_message chứa ký tự \n bên trong nội dung comment
# → Nếu đếm dòng bằng len(open(file).readlines()) sẽ bị SAI (đếm thừa)
# → Giải pháp: Dùng pandas đọc lại và đếm len(df)
row_count = len(pd.read_csv(filepath))  # Đếm chính xác
```

### Quy trình load

```python
for table_name, df in tables.items():
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists='replace',  # Xóa bảng cũ và tạo mới (idempotent)
        index=False,           # Không tạo cột index thừa
        chunksize=5000         # Load 5000 dòng/lần để tránh timeout
    )
```

**Tại sao dùng `if_exists='replace'`?**
> Đảm bảo tính **idempotent** — chạy script bao nhiêu lần cũng cho kết quả giống nhau. Nếu dùng `append`, chạy lại sẽ bị trùng lặp dữ liệu.

---

## Script 4: `04_star_schema_builder.py`

### Mục đích
Biến 8 bảng normalized (chuẩn 3NF) thành kiến trúc **Star Schema** tối ưu cho Power BI: 1 bảng Fact trung tâm + 4 bảng Dimension xung quanh.

### Tại sao cần Star Schema?
> Bảng normalized (3NF) tốt cho hệ thống transactional (OLTP) nhưng RẤT CHẬM khi phân tích (phải JOIN nhiều bảng). Star Schema được thiết kế riêng cho phân tích (OLAP) — ít JOIN, truy vấn nhanh, Power BI hiểu ngay cấu trúc.

### Quy trình xây dựng từng bảng

#### 1. Dim_Date (Bảng lịch)

```python
# Tạo dải ngày LIÊN TỤC từ 01/01/2016 đến 31/12/2018
# (Dài hơn dữ liệu thực để Power BI Time Intelligence hoạt động đúng)
date_range = pd.date_range(start='2016-01-01', end='2018-12-31', freq='D')

dim_date = pd.DataFrame({'date': date_range})
dim_date['date_key']    = dim_date['date'].dt.strftime('%Y%m%d').astype(int)  # 20170115
dim_date['year']        = dim_date['date'].dt.year
dim_date['quarter']     = dim_date['date'].dt.quarter
dim_date['month']       = dim_date['date'].dt.month
dim_date['month_name']  = dim_date['date'].dt.strftime('%B')      # January, February...
dim_date['day_of_week'] = dim_date['date'].dt.dayofweek            # 0=Monday
dim_date['day_name']    = dim_date['date'].dt.strftime('%A')       # Monday, Tuesday...
dim_date['year_month']  = dim_date['date'].dt.strftime('%Y-%m')    # 2017-01
```

**Tại sao dải ngày phải LIÊN TỤC (không có gap)?**
> Các hàm Time Intelligence của Power BI (DATESYTD, SAMEPERIODLASTYEAR, DATEADD) yêu cầu Date table phải có đầy đủ mọi ngày — không được thiếu bất kỳ ngày nào. Nếu thiếu ngày 15/03/2017, hàm YTD sẽ tính sai.

#### 2. Dim_Customers

```python
# Chỉ giữ 1 dòng duy nhất cho mỗi khách hàng unique
# (Vì 1 khách hàng có thể đặt nhiều đơn hàng → nhiều dòng trong bảng orders)
dim_customers = customers[['customer_unique_id', 'customer_city', 
                            'customer_state', 'customer_zip_code_prefix']
                          ].drop_duplicates(subset='customer_unique_id')
```

#### 3. Dim_Products

```python
dim_products = products[['product_id', 'category', 
                         'product_weight_g', 'product_length_cm',
                         'product_height_cm', 'product_width_cm']
                       ].drop_duplicates(subset='product_id')
```

#### 4. Fact_Order_Items (Bảng thực tế)

```python
# GRAIN (Hạt nhân): 1 dòng = 1 sản phẩm trong 1 đơn hàng
# Đây là mức chi tiết nhất có thể

# Merge nhiều bảng lại để tạo bảng Fact "phẳng"
fact = order_items.merge(orders, on='order_id')     \
                  .merge(payments_agg, on='order_id', how='left')

# Tính các metric vận hành (pre-computed để DAX chạy nhanh)
fact['delivery_days'] = (
    fact['order_delivered_customer_date'] - fact['order_purchase_timestamp']
).dt.days

fact['delivery_delay_days'] = (
    fact['order_delivered_customer_date'] - fact['order_estimated_delivery_date']
).dt.days

# Cờ giao trễ: 1 = trễ, 0 = đúng hạn hoặc sớm
fact['is_late_delivery'] = (fact['delivery_delay_days'] > 0).astype('Int64')
```

**Tại sao tính sẵn `delivery_days` trong Python thay vì tính bằng DAX?**
> DAX tính toán trên từng dòng khi render biểu đồ → rất chậm với 113K dòng. Python tính trước 1 lần duy nhất → Power BI chỉ cần SUM/AVERAGE, nhanh gấp 10-50 lần.

---

## Tổng Kết Kỹ Thuật

| Quyết định | Lý do |
|-----------|-------|
| `errors='coerce'` khi parse datetime | An toàn cho production, không crash khi gặp dữ liệu bẩn |
| Giữ NaT thay vì fillna cho delivery dates | MNAR — missing có ý nghĩa kinh doanh |
| Flag outlier thay vì xóa | Bảo toàn tính chính xác của GMV |
| LEFT JOIN khi dịch category | Không mất sản phẩm thiếu bản dịch |
| `if_exists='replace'` khi load SQL | Đảm bảo idempotent (chạy lại an toàn) |
| Pre-compute metrics trong Fact table | DAX performance tối ưu |
| Date range liên tục (không gap) | Yêu cầu bắt buộc cho Time Intelligence |
