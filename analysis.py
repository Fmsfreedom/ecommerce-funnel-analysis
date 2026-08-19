"""
电商营销漏斗分析 —— 指标计算与可视化

使用 SQL 从 SQLite 提取数据，计算转化漏斗、复购率、RFM 客户分层，
并生成可视化图表与报告。
"""
import os
import sqlite3
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

os.makedirs("output", exist_ok=True)

conn = sqlite3.connect("ecommerce.db")

# ===== 1. 转化漏斗（SQL）=====
funnel_query = """
WITH step1 AS (SELECT DISTINCT user_id FROM events WHERE event_type = 'browse'),
     step2 AS (SELECT DISTINCT user_id FROM events WHERE event_type = 'add_to_cart'),
     step3 AS (SELECT DISTINCT user_id FROM events WHERE event_type = 'order_created'),
     step4 AS (SELECT DISTINCT user_id FROM events WHERE event_type = 'payment_success')
SELECT
  (SELECT COUNT(*) FROM step1) AS browse_users,
  (SELECT COUNT(*) FROM step2) AS cart_users,
  (SELECT COUNT(*) FROM step3) AS order_users,
  (SELECT COUNT(*) FROM step4) AS pay_users;
"""
funnel = pd.read_sql(funnel_query, conn).iloc[0]

b, c, o, p = (
    funnel["browse_users"],
    funnel["cart_users"],
    funnel["order_users"],
    funnel["pay_users"],
)
print("=" * 50)
print("转化漏斗")
print("=" * 50)
print(f"浏览：{b} 人")
print(f"加购：{c} 人（浏览→加购：{c / b * 100:.2f}%）")
print(f"下单：{o} 人（加购→下单：{o / c * 100:.2f}%）")
print(f"支付：{p} 人（下单→支付：{p / o * 100:.2f}%）")
print(f"整体转化：{p / b * 100:.2f}%")

# ===== 2. 复购率 =====
repurchase_query = """
WITH pay_users AS (
  SELECT user_id, COUNT(*) AS pay_cnt
  FROM events WHERE event_type = 'payment_success'
  GROUP BY user_id
)
SELECT
  SUM(CASE WHEN pay_cnt >= 2 THEN 1 ELSE 0 END) AS repeat_buyers,
  COUNT(*) AS total_buyers,
  ROUND(SUM(CASE WHEN pay_cnt >= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS repurchase_rate
FROM pay_users;
"""
rep = pd.read_sql(repurchase_query, conn).iloc[0]
print(f"\n复购用户：{rep['repeat_buyers']} / {rep['total_buyers']}")
print(f"复购率：{rep['repurchase_rate']}%")

# ===== 3. RFM 客户分层 =====
rfm_query = """
WITH pay_data AS (
  SELECT
    user_id,
    MAX(event_time) AS last_pay,
    COUNT(*) AS frequency,
    SUM(amount) AS monetary
  FROM events
  WHERE event_type = 'payment_success'
  GROUP BY user_id
),
rfm AS (
  SELECT
    user_id,
    CAST(julianday('2024-12-31') - julianday(last_pay) AS INT) AS recency,
    frequency,
    monetary
  FROM pay_data
)
SELECT * FROM rfm;
"""
rfm = pd.read_sql(rfm_query, conn)

# 五等分打分
rfm["R_score"] = pd.qcut(rfm["recency"], 5, labels=[5, 4, 3, 2, 1])  # 越近越高
rfm["F_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
rfm["M_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
rfm["RFM_score"] = (
    rfm["R_score"].astype(str) + rfm["F_score"].astype(str) + rfm["M_score"].astype(str)
)


def segment(s):
    r, f, m = int(s[0]), int(s[1]), int(s[2])
    if r >= 4 and f >= 4 and m >= 4:
        return "高价值客户"
    elif r >= 3 and f >= 3:
        return "忠诚客户"
    elif r >= 4:
        return "新客户"
    elif f >= 3:
        return "常购客户"
    else:
        return "流失风险客户"


rfm["segment"] = rfm["RFM_score"].apply(segment)
print("\nRFM 客户分层：")
print(rfm["segment"].value_counts())

# ===== 4. 可视化 =====
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 漏斗图（条形图模拟）
stages = ["浏览", "加购", "下单", "支付"]
values = [b, c, o, p]
axes[0].barh(stages[::-1], values[::-1], color=["#378add", "#639922", "#ba7517", "#d85a30"])
axes[0].set_title("转化漏斗（用户数）")
axes[0].set_xlabel("用户数")
for i, v in enumerate(values[::-1]):
    axes[0].text(v + 20, i, str(v), va="center")

# RFM 分层饼图
seg_counts = rfm["segment"].value_counts()
axes[1].pie(seg_counts, labels=seg_counts.index, autopct="%1.1f%%", startangle=90)
axes[1].set_title("RFM 客户分层")

plt.tight_layout()
plt.savefig("output/funnel_rfm.png", dpi=150)
plt.close()

# ===== 4.5 渠道分析 =====
channel_query = """
SELECT u.channel,
       COUNT(DISTINCT u.user_id) AS users,
       COUNT(DISTINCT CASE WHEN e.event_type='payment_success' THEN u.user_id END) AS buyers,
       ROUND(COUNT(DISTINCT CASE WHEN e.event_type='payment_success' THEN u.user_id END) * 100.0 / COUNT(DISTINCT u.user_id), 2) AS conv_rate
FROM users u LEFT JOIN events e ON u.user_id = e.user_id
GROUP BY u.channel
ORDER BY buyers DESC;
"""
channel = pd.read_sql(channel_query, conn)
print("\n各渠道用户与转化：")
print(channel.to_string(index=False))

# ===== 4.6 用户留存分析（cohort） =====
users_df = pd.read_sql("SELECT user_id, register_date, channel FROM users", conn, parse_dates=["register_date"])
events = pd.read_sql("SELECT user_id, event_type, event_time, product_name, sku, amount FROM events", conn, parse_dates=["event_time"])

# ===== 4.55 商品 GMV 拆解（SKU 粒度） =====
product_gmv = events[events["event_type"] == "payment_success"].groupby("product_name")["amount"].agg(
    GMV="sum", 订单数="count"
).sort_values("GMV", ascending=False)
sku_gmv = events[events["event_type"] == "payment_success"].groupby("sku")["amount"].agg(
    GMV="sum", 订单数="count"
).sort_values("GMV", ascending=False).head(10)
print("\n商品 GMV 拆解（按商品）：")
print(product_gmv.round(2).to_string())
print("\nSKU 粒度 GMV TOP10：")
print(sku_gmv.round(2).to_string())

# 留存活跃 = 注册后第 N 月有任一事件（浏览/加购/支付）的用户
all_events = events[["user_id", "event_time"]].copy()
all_events["event_month"] = pd.to_datetime(all_events["event_time"]).dt.to_period("M").astype(str)
users_df["register_month"] = users_df["register_date"].dt.to_period("M").astype(str)

cohort = users_df[["user_id", "register_month"]].merge(all_events, on="user_id")
r_dt = pd.to_datetime(cohort["register_month"])
p_dt = pd.to_datetime(cohort["event_month"])
cohort["mob"] = (p_dt.dt.year - r_dt.dt.year) * 12 + (p_dt.dt.month - r_dt.dt.month)

cohort_size = users_df.groupby("register_month")["user_id"].nunique().reset_index().rename(columns={"user_id": "cohort_size"})
retention = cohort.groupby(["register_month", "mob"])["user_id"].nunique().reset_index()
retention = retention.merge(cohort_size, on="register_month")
retention["retention_rate"] = retention["user_id"] / retention["cohort_size"] * 100

retention_pivot = retention[retention["mob"] <= 5].pivot_table(
    index="register_month", columns="mob", values="retention_rate"
).round(2)
print("\n用户留存矩阵（注册月 cohort，列为 MOB 0-5）：")
print(retention_pivot)

# 渠道 + 留存出图
fig, axes = plt.subplots(1, 2, figsize=(16, 5))

ax = axes[0]
x = range(len(channel))
ax.bar(x, channel["users"], color="#378add", label="注册用户", alpha=0.6)
ax2 = ax.twinx()
ax2.plot(x, channel["conv_rate"], marker="o", color="#d85a30", label="转化率%")
ax.set_xticks(list(x))
ax.set_xticklabels(channel["channel"], rotation=20)
ax.set_title("各渠道用户数与转化率")
ax.legend(loc="upper left")
ax2.legend(loc="upper right")

ax = axes[1]
im = ax.imshow(retention_pivot.values, aspect="auto", cmap="YlOrRd")
ax.set_xticks(range(len(retention_pivot.columns)))
ax.set_xticklabels([f"M+{c}" for c in retention_pivot.columns])
ax.set_yticks(range(len(retention_pivot.index)))
ax.set_yticklabels(retention_pivot.index)
ax.set_title("用户留存矩阵（cohort × MOB）")
plt.colorbar(im, ax=ax, label="留存率 %")
for i in range(len(retention_pivot.index)):
    for j in range(len(retention_pivot.columns)):
        v = retention_pivot.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                    color="white" if v > retention_pivot.values.max() / 2 else "black", fontsize=8)

plt.tight_layout()
plt.savefig("output/channel_retention.png", dpi=150)
plt.close()

# ===== 5. 报告 =====
report = [
    "# 电商营销漏斗分析报告",
    "",
    "## 转化漏斗",
    f"- 浏览：{b} 人",
    f"- 加购：{c} 人（浏览→加购：{c / b * 100:.2f}%）",
    f"- 下单：{o} 人（加购→下单：{o / c * 100:.2f}%）",
    f"- 支付：{p} 人（下单→支付：{p / o * 100:.2f}%）",
    f"- 整体转化：{p / b * 100:.2f}%",
    "",
    "## 复购率",
    f"- 复购用户：{rep['repeat_buyers']} / {rep['total_buyers']}",
    f"- 复购率：{rep['repurchase_rate']}%",
    "",
    "## RFM 客户分层",
    rfm["segment"].value_counts().to_string(),
    "",
    "## 图表",
    "- output/funnel_rfm.png",
]
with open("output/report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print("\n分析完成")
conn.close()
