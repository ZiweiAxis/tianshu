# E2-S2：飞书 ↔ Matrix 事件类型与内容转换（可维护映射）

import json
from typing import Any, Dict, Tuple

# 飞书消息类型 -> Matrix msgtype
FEISHU_TO_MATRIX_MSGTYPE: Dict[str, str] = {
    "text": "m.text",
    "post": "m.text",  # 富文本先按文本处理
    "interactive": "m.text",  # 卡片回调等，body 可放摘要或 JSON 引用
}

# Matrix msgtype -> 飞书 msg_type
MATRIX_TO_FEISHU_MSGTYPE: Dict[str, str] = {
    "m.text": "text",
    "m.notice": "text",
}


def feishu_event_to_matrix(feishu_event: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    将飞书事件转为 Matrix 可发送的 (msgtype, content)。
    feishu_event 预期为事件体，如 event.message.content（文本）或 event 顶层含 message 等。
    返回 (msgtype, content)，content 为 room_send 的 content 字典。
    """
    msg_type = (feishu_event.get("message", {}) or {}).get("message_type") or feishu_event.get("message_type", "text")
    matrix_msgtype = FEISHU_TO_MATRIX_MSGTYPE.get(msg_type, "m.text")

    content = feishu_event.get("message", {}).get("content") or feishu_event.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content) if content.strip().startswith("{") else {"text": content}
        except json.JSONDecodeError:
            content = {"text": content}
    text = content.get("text") or content.get("content") or ""

    return matrix_msgtype, {"msgtype": matrix_msgtype, "body": text or "(无文本)"}


def matrix_event_to_feishu(room_id: str, msgtype: str, content: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Matrix 事件转为飞书发消息 API 所需格式。
    返回 {"msg_type": "text", "content": {"text": "..."}} 等。
    """
    feishu_msg_type = MATRIX_TO_FEISHU_MSGTYPE.get(msgtype, "text")
    body = content.get("body") or content.get("content", {}).get("body") or ""
    return {"msg_type": feishu_msg_type, "content": {"text": body}}
