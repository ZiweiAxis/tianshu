# E7-S1 / E1-S1：消息/事件带可审计字段
# 唯一 ID、收发方、可信时间戳，供谛听拉取与追溯

import time
import uuid
from typing import Any, Dict


def inject_audit_fields(
    content: Dict[str, Any],
    sender: str = "",
    receiver: str = "",
    message_id: str = "",
) -> Dict[str, Any]:
    """为 content 注入 message_id、sender、receiver、timestamp（可审计）。"""
    out = dict(content)
    out["message_id"] = message_id or str(uuid.uuid4())
    out["sender"] = sender
    out["receiver"] = receiver
    out["timestamp"] = time.time()
    return out
