from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DemoStore:
    customers: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def seeded(cls) -> "DemoStore":
        now = _now()
        store = cls()
        store.customers = {
            "user_demo": {
                "customer_id": "cust_1001",
                "name": "Lin",
                "tier": "vip",
                "email_masked": "li***@example.com",
                "phone_masked": "138****0001",
                "verified": True,
            },
            "user_guest": {
                "customer_id": "cust_2001",
                "name": "Guest",
                "tier": "standard",
                "email_masked": None,
                "phone_masked": None,
                "verified": False,
            },
        }
        store.orders = {
            "A1001": {
                "order_id": "A1001",
                "customer_id": "cust_1001",
                "status": "delivered",
                "product": "Nimbus Noise-cancelling Headphones",
                "amount": 1299,
                "currency": "CNY",
                "delivered_at": (now - timedelta(days=2)).isoformat(),
                "logistics_id": "SF123456789CN",
                "returnable": True,
            },
            "A1002": {
                "order_id": "A1002",
                "customer_id": "cust_1001",
                "status": "shipped",
                "product": "Orbit Keyboard",
                "amount": 699,
                "currency": "CNY",
                "delivered_at": None,
                "logistics_id": "YT99887766CN",
                "returnable": False,
            },
            "B2001": {
                "order_id": "B2001",
                "customer_id": "cust_2001",
                "status": "paid",
                "product": "Cloud Mug",
                "amount": 89,
                "currency": "CNY",
                "delivered_at": None,
                "logistics_id": None,
                "returnable": False,
            },
        }
        return store


KNOWLEDGE_DOCUMENTS = [
    {
        "document_id": "return_policy_v3",
        "title": "退换货政策 v3",
        "source_uri": "kb://policies/return_policy_v3",
        "content": (
            "退换货政策 v3。已签收商品如存在质量问题，可在签收后 30 天内申请退货或换货。"
            "无质量问题的耳机、键盘等商品，需保持包装完整且不影响二次销售。"
            "超过 30 天的订单不能承诺自动退款，应转人工复核。"
        ),
        "metadata": {"version": "v3", "effective": "2026-01-01"},
    },
    {
        "document_id": "shipping_policy_v2",
        "title": "物流查询与延迟处理 v2",
        "source_uri": "kb://policies/shipping_policy_v2",
        "content": (
            "物流政策 v2。已发货订单应先查询物流单号和当前节点。"
            "如超过承诺到达时间 48 小时仍无更新，应创建物流跟进工单。"
            "客服不能直接承诺赔付金额，只能说明会由专员核实。"
        ),
        "metadata": {"version": "v2", "effective": "2026-03-15"},
    },
    {
        "document_id": "invoice_policy_v1",
        "title": "发票与账单政策 v1",
        "source_uri": "kb://policies/invoice_policy_v1",
        "content": (
            "发票政策 v1。电子发票通常在付款后 24 小时内开具。"
            "抬头或税号错误时，需核验订单和企业信息后创建发票修改工单。"
        ),
        "metadata": {"version": "v1", "effective": "2025-11-01"},
    },
    {
        "document_id": "security_policy_v2",
        "title": "账号安全与隐私政策 v2",
        "source_uri": "kb://policies/security_policy_v2",
        "content": (
            "账号安全政策 v2。未完成身份验证时，不能展示完整手机号、地址、邮箱或订单金额明细。"
            "遇到账户被盗、异常登录、支付争议，应立即升级人工安全队列。"
        ),
        "metadata": {"version": "v2", "effective": "2026-02-10"},
    },
    {
        "document_id": "troubleshooting_audio_v1",
        "title": "耳机故障排查 v1",
        "source_uri": "kb://guides/troubleshooting_audio_v1",
        "content": (
            "耳机故障排查 v1。单边无声时，先确认蓝牙连接、重置配对、清洁充电触点，"
            "再尝试固件升级。若仍无法恢复，应结合订单状态判断是否走售后。"
        ),
        "metadata": {"version": "v1", "effective": "2026-04-20"},
    },
]

