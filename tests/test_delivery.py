# E2-S3 验收：出站投递经 Matrix 事件

import pytest

from src.core.delivery import (
    DELIVERY_MSGTYPE,
    build_delivery_content,
    is_delivery_event,
    parse_delivery_event,
)


def test_build_delivery_content():
    content = build_delivery_content(
        "alert_notification",
        {"channel": "feishu", "receive_id": "oc_xxx", "receive_id_type": "chat_id"},
        {"title": "告警", "body": "内容"},
        body_summary="摘要",
    )
    assert content["msgtype"] == DELIVERY_MSGTYPE
    assert content["semantic_type"] == "alert_notification"
    assert content["target"]["channel"] == "feishu"
    assert content["target"]["receive_id"] == "oc_xxx"
    assert content["payload"]["title"] == "告警"


def test_is_delivery_event():
    assert is_delivery_event(DELIVERY_MSGTYPE, {}) is True
    assert is_delivery_event("m.text", {"msgtype": DELIVERY_MSGTYPE}) is True
    assert is_delivery_event("m.text", {"msgtype": "m.text"}) is False


def test_parse_delivery_event():
    content = build_delivery_content(
        "text",
        {"channel": "feishu", "receive_id": "ou_yyy", "receive_id_type": "open_id"},
        {"text": "hello"},
    )
    out = parse_delivery_event(content)
    assert out is not None
    sem, target, payload = out
    assert sem == "text"
    assert target["receive_id"] == "ou_yyy"
    assert payload["text"] == "hello"


def test_channel_adapter_semantic_to_feishu():
    """渠道适配层：非卡片语义 -> 飞书文本。"""
    from src.channel_adapter import semantic_to_feishu_message
    out = semantic_to_feishu_message("alert_notification", {"title": "标题", "body": "内容"})
    assert out["msg_type"] == "text"
    assert "标题" in out["content"]["text"] or "内容" in out["content"]["text"]


def test_channel_adapter_dashboard_summary_card():
    """E2-S4：dashboard_summary -> 飞书 interactive 卡片。"""
    from src.channel_adapter import semantic_to_feishu_message
    out = semantic_to_feishu_message(
        "dashboard_summary",
        {"participant_count": 10, "agent_count": 2, "deliver_rate": "98%"},
    )
    assert out["msg_type"] == "interactive"
    c = out["content"]
    assert "header" in c and "elements" in c
    assert "运维大盘摘要" in str(c["header"])
    assert "10" in str(c["elements"]) and "2" in str(c["elements"])


def test_channel_adapter_approval_request_card():
    """E2-S4：approval_request -> 飞书 interactive 卡片。"""
    from src.channel_adapter import semantic_to_feishu_message
    out = semantic_to_feishu_message("approval_request", {"title": "请审批", "description": "描述内容"})
    assert out["msg_type"] == "interactive"
    c = out["content"]
    assert "请审批" in str(c["header"])
    assert "描述内容" in str(c["elements"])


def test_parse_delivery_event_invalid():
    assert parse_delivery_event({}) is None
    assert parse_delivery_event({"msgtype": "m.text"}) is None
    assert parse_delivery_event({"msgtype": DELIVERY_MSGTYPE, "target": {}}) is None


@pytest.mark.asyncio
async def test_handle_delivery_event():
    from src.bridge import feishu
    from src.core.delivery import build_delivery_content

    sent = []

    class FakeFeishu:
        async def send_message(self, receive_id, receive_id_type, msg_type, content):
            sent.append((receive_id, receive_id_type, msg_type, content))
            return "msg_123"

    class FakeAdapter:
        @staticmethod
        def semantic_to_feishu_message(semantic_type, payload):
            return {"msg_type": "text", "content": {"text": f"{semantic_type}: {payload.get('body', '')}"}}

    content = build_delivery_content(
        "alert_notification",
        {"channel": "feishu", "receive_id": "oc_room1", "receive_id_type": "chat_id"},
        {"body": "test alert"},
    )
    ok = await feishu.handle_delivery_event(
        "!r:hs", DELIVERY_MSGTYPE, content, FakeFeishu(), FakeAdapter()
    )
    assert ok is True
    assert len(sent) == 1
    assert sent[0][0] == "oc_room1"
    assert sent[0][2] == "text"
    assert "alert_notification" in sent[0][3]["text"] or "test alert" in sent[0][3]["text"]


@pytest.mark.asyncio
async def test_handle_delivery_event_non_feishu_skip():
    from src.bridge import feishu
    from src.core.delivery import build_delivery_content

    content = build_delivery_content(
        "text",
        {"channel": "dingtalk", "receive_id": "xxx", "receive_id_type": "chat_id"},
        {"text": "hi"},
    )
    ok = await feishu.handle_delivery_event("!r:hs", DELIVERY_MSGTYPE, content, None, None)
    assert ok is False
