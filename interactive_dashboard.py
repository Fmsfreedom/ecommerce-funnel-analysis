"""
电商营销交互式看板（Plotly）

生成交互式 HTML 看板：转化漏斗 / 渠道转化 / 留存热力图 / RFM 分层。
浏览器打开 output/dashboard.html 即可交互查看。
"""
import os
import sqlite3

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

os.makedirs("output", exist_ok=True)

conn = sqlite3.connect("ecommerce.db")

# ---- 漏斗 ----
funnel_query = """
WITH step1 AS (SELECT DISTINCT user_id FROM events WHERE event_type='browse'),
     step2 AS (SELECT DISTINCT user_id FROM events WHERE event_type='add_to_cart'),
     step3 AS (SELECT DISTINCT user_id FROM events WHERE event_type='order_created'),
     step4 AS (SELECT DISTINCT user_id FROM events WHERE event_type='payment_success')
SELECT (SELECT COUNT(*) FROM step1) b, (SELECT COUNT(*) FROM step2) c,
       (SELECT COUNT(*) FROM step3) o, (SELECT COUNT(*) FROM step4) p;
"""
f = pd.read_sql(funnel_query, conn).iloc[0]
b, c, o, p = int(f["b"]), int(f["c"]), int(f["o"]), int(f["p"])

# ---- 渠道 ----
channel = pd.read_sql(
    """
    SELECT u.channel,
           COUNT(DISTINCT u.user_id) AS users,
           COUNT(DISTINCT CASE WHEN e.event_type='payment_success' THEN u.user_id END) AS buyers
    FROM users u LEFT JOIN events e ON u.user_id = e.user_id
    GROUP BY u.channel ORDER BY buyers DESC
    """,
    conn,
)
channel["conv_rate"] = channel["buyers"] / channel["users"] * 100

# ---- RFM ----
rfm = pd.read_sql(
    """
    WITH pay AS (
        SELECT user_id, MAX(event_time) AS last_pay, COUNT(*) AS freq, SUM(amount) AS mon
        FROM events WHERE event_type='payment_success' GROUP BY user_id
    )
    SELECT user_id, CAST(julianday('2024-12-31') - julianday(last_pay) AS INT) AS recency,
           freq, mon FROM pay
    """,
    conn,
)
rfm["R"] = pd.qcut(rfm["recency"], 5, labels=[5, 4, 3, 2, 1])
rfm["F"] = pd.qcut(rfm["freq"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
rfm["M"] = pd.qcut(rfm["mon"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])


def seg(s):
    r, ff, m = int(s[0]), int(s[1]), int(s[2])
    if r >= 4 and ff >= 4 and m >= 4:
        return "高价值客户"
    if r >= 3 and ff >= 3:
        return "忠诚客户"
    if r >= 4:
        return "新客户"
    if ff >= 3:
        return "常购客户"
    return "流失风险客户"


rfm["segment"] = (rfm["R"].astype(str) + rfm["F"].astype(str) + rfm["M"].astype(str)).apply(seg)
seg_counts = rfm["segment"].value_counts()

# ---- 留存 ----
users_df = pd.read_sql("SELECT user_id, register_date FROM users", conn, parse_dates=["register_date"])
events = pd.read_sql("SELECT user_id, event_time FROM events", conn, parse_dates=["event_time"])
events["event_month"] = events["event_time"].dt.to_period("M").astype(str)
users_df["register_month"] = users_df["register_date"].dt.to_period("M").astype(str)
cohort = users_df[["user_id", "register_month"]].merge(events, on="user_id")
rdt = pd.to_datetime(cohort["register_month"])
pdt = pd.to_datetime(cohort["event_month"])
cohort["mob"] = (pdt.dt.year - rdt.dt.year) * 12 + (pdt.dt.month - rdt.dt.month)
cohort_size = users_df.groupby("register_month")["user_id"].nunique().rename("size")
ret = cohort.groupby(["register_month", "mob"])["user_id"].nunique().reset_index()
ret = ret.merge(cohort_size, on="register_month")
ret["rate"] = ret["user_id"] / ret["size"] * 100
retention_pivot = ret[ret["mob"] <= 5].pivot_table(index="register_month", columns="mob", values="rate").round(2)

conn.close()

# ---- 看板 ----
fig = make_subplots(
    rows=2,
    cols=2,
    specs=[[{"type": "funnel"}, {"type": "bar"}], [{"type": "heatmap"}, {"type": "pie"}]],
    subplot_titles=("转化漏斗", "各渠道转化率（%）", "用户留存矩阵（cohort × MOB）", "RFM 客户分层"),
)

fig.add_trace(
    go.Funnel(x=[b, c, o, p], y=["浏览", "加购", "下单", "支付"], textinfo="value+percent previous"),
    row=1, col=1,
)

fig.add_trace(
    go.Bar(x=channel["channel"], y=channel["conv_rate"], marker_color="#378add", text=channel["conv_rate"].round(2), textposition="outside"),
    row=1, col=2,
)

fig.add_trace(
    go.Heatmap(
        z=retention_pivot.values,
        x=[f"M+{c}" for c in retention_pivot.columns],
        y=retention_pivot.index,
        colorscale="YlOrRd",
        colorbar=dict(title="留存率%"),
    ),
    row=2, col=1,
)

fig.add_trace(go.Pie(labels=seg_counts.index, values=seg_counts.values), row=2, col=2)

fig.update_layout(
    title=f"电商营销交互式看板 ｜ 整体转化率 {p / b * 100:.2f}% · 支付 {p} 人",
    height=800,
    showlegend=False,
)
fig.write_html("output/dashboard.html")
print("交互式看板已生成：output/dashboard.html")
