"""
电商营销漏斗分析 —— 模拟用户行为数据生成

生成模拟的跨境电商用户行为数据（浏览 / 加购 / 下单 / 支付），
写入 SQLite 数据库 ecommerce.db，包含 users、events 两张表。
数据为随机生成，仅用于演示分析方法。
"""
import random

import numpy as np
import pandas as pd
import sqlite3

np.random.seed(42)
random.seed(42)

N_USERS = 5000
PLATFORMS = ["App", "Web", "MiniProgram"]
CHANNELS = ["抖音", "小红书", "微信", "直通车", "自然搜索"]
COUNTRIES = ["美国", "英国", "德国", "法国", "日本", "韩国", "加拿大", "澳大利亚"]

# 商品目录：商品名 → SKU 变体（用于 SKU 粒度 GMV 拆解）
PRODUCT_CATALOG = {
    "无线耳机": ["黑色", "白色", "标准款", "Pro款"],
    "智能手表": ["黑色", "银色", "运动款", "经典款"],
    "充电宝": ["10000mAh", "20000mAh", "快充款"],
    "蓝牙音箱": ["黑色", "蓝色", "防水款"],
    "手机壳": ["透明", "磨砂", "硅胶", "磁吸"],
    "数据线": ["1m", "2m", "编织款"],
    "香薰机": ["白色", "木纹", "静音款"],
    "筋膜枪": ["标准款", "Mini款", "专业款"],
    "太阳镜": ["黑色", "棕色", "偏光款"],
    "保温杯": ["350ml", "500ml", "智能款"],
}
PRODUCT_NAMES = list(PRODUCT_CATALOG.keys())


def rand_product():
    """随机返回一个商品及其 SKU"""
    name = random.choice(PRODUCT_NAMES)
    sku = f"{name}-{random.choice(PRODUCT_CATALOG[name])}"
    return name, sku


# 生成用户
user_ids = [f"U{i:06d}" for i in range(1, N_USERS + 1)]
register_dates = pd.to_datetime("2024-01-01") + pd.to_timedelta(
    np.random.randint(0, 365, N_USERS), unit="D"
)
channels = np.random.choice(CHANNELS, size=N_USERS, p=[0.25, 0.20, 0.15, 0.20, 0.20])
countries = np.random.choice(COUNTRIES, size=N_USERS, p=[0.30, 0.12, 0.12, 0.10, 0.12, 0.10, 0.08, 0.06])

users = pd.DataFrame(
    {
        "user_id": user_ids,
        "register_date": register_dates,
        "channel": channels,
        "country": countries,
    }
)

# 生成事件
events_list = []
for uid, reg_date in zip(user_ids, register_dates):
    # 浏览：5-50 次
    n_browse = np.random.randint(5, 50)
    browse_times = reg_date + pd.to_timedelta(np.random.randint(0, 300, n_browse) * 24, unit="h")
    for t in browse_times:
        name, sku = rand_product()
        events_list.append((uid, "browse", t, np.random.choice(PLATFORMS), name, sku, 0.0))

    # 加购：30% 概率
    if np.random.rand() < 0.30:
        n_cart = np.random.randint(1, 5)
        cart_times = reg_date + pd.to_timedelta(
            np.random.randint(0, 300, n_cart) * 24, unit="h"
        )
        for t in cart_times:
            name, sku = rand_product()
            events_list.append(
                (
                    uid,
                    "add_to_cart",
                    t,
                    np.random.choice(PLATFORMS),
                    name,
                    sku,
                    round(np.random.uniform(20, 500), 2),
                )
            )

    # 下单：12% 概率
    if np.random.rand() < 0.12:
        n_order = np.random.randint(1, 3)
        order_times = reg_date + pd.to_timedelta(
            np.random.randint(0, 300, n_order) * 24, unit="h"
        )
        for t in order_times:
            name, sku = rand_product()
            events_list.append(
                (
                    uid,
                    "order_created",
                    t,
                    np.random.choice(PLATFORMS),
                    name,
                    sku,
                    round(np.random.uniform(50, 800), 2),
                )
            )

    # 支付：9% 概率
    if np.random.rand() < 0.09:
        n_pay = np.random.randint(1, 3)
        pay_times = reg_date + pd.to_timedelta(
            np.random.randint(0, 300, n_pay) * 24, unit="h"
        )
        for t in pay_times:
            name, sku = rand_product()
            events_list.append(
                (
                    uid,
                    "payment_success",
                    t,
                    np.random.choice(PLATFORMS),
                    name,
                    sku,
                    round(np.random.uniform(50, 800), 2),
                )
            )

events = pd.DataFrame(
    events_list,
    columns=["user_id", "event_type", "event_time", "platform", "product_name", "sku", "amount"],
)
events = events.sort_values("event_time").reset_index(drop=True)

# 写入 SQLite
conn = sqlite3.connect("ecommerce.db")
users.to_sql("users", conn, if_exists="replace", index=False)
events.to_sql("events", conn, if_exists="replace", index=False)
conn.close()

print(f"已生成 {len(users)} 个用户，{len(events)} 条事件，存入 ecommerce.db")
print("\n事件类型分布：")
print(events["event_type"].value_counts())
