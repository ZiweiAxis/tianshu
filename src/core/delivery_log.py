# E6-S3：投递状态日志——未触达/已触达/失败/被拒绝可区分、可查询

import time
import uuid
from typing import Any, Dict, List, Optional

# 状态：pending -> delivered | failed | rejected | no_reply
STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
STATUS_NO_REPLY = "no_reply"

_log: List[Dict[str, Any]] = []
_max_entries = 5000


def _trim():
    global _log
    if len(_log) > _max_entries:
        _log = _log[-_max_entries:]


def record_delivery_start(
    semantic_type: str,
    target: Dict[str, Any],
    payload_summary: Optional[str] = None,
    delivery_id: Optional[str] = None,
) -> str:
    """
    记录一次投递开始，返回 delivery_id。
    target 含 channel、receive_id、receive_id_type 等。
    """
    did = delivery_id or str(uuid.uuid4())
    entry = {
        "delivery_id": did,
        "semantic_type": semantic_type,
        "target": dict(target),
        "payload_summary": payload_summary or "",
        "status": STATUS_PENDING,
        "started_at": time.time(),
        "updated_at": time.time(),
        "feishu_message_id": None,
        "error_reason": None,
    }
    _log.append(entry)
    _trim()
    return did


def record_delivery_done(
    delivery_id: str,
    status: str,
    feishu_message_id: Optional[str] = None,
    error_reason: Optional[str] = None,
) -> bool:
    """更新投递结果为 delivered / failed / rejected / no_reply。"""
    for e in reversed(_log):
        if e.get("delivery_id") == delivery_id:
            e["status"] = status
            e["updated_at"] = time.time()
            if feishu_message_id is not None:
                e["feishu_message_id"] = feishu_message_id
            if error_reason is not None:
                e["error_reason"] = error_reason
            return True
    return False


def query_delivery_log(
    delivery_id: Optional[str] = None,
    by_time_range: Optional[tuple] = None,
    by_receive_id: Optional[str] = None,
    by_status: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    查询投递日志，供运维/Bot 排障。
    by_time_range: (start_ts, end_ts) 可选
    by_receive_id: 目标 receive_id（飞书 chat_id/open_id）
    by_status: pending | delivered | failed | rejected | no_reply
    返回 { "items": [...], "total": N }，每条含 delivery_id、semantic_type、target、status、started_at、updated_at、feishu_message_id、error_reason。
    """
    items = list(_log)
    if delivery_id:
        items = [e for e in items if e.get("delivery_id") == delivery_id]
    if by_time_range:
        start_ts, end_ts = by_time_range
        items = [e for e in items if start_ts <= e.get("started_at", 0) <= end_ts]
    if by_receive_id:
        items = [e for e in items if (e.get("target") or {}).get("receive_id") == by_receive_id]
    if by_status:
        items = [e for e in items if e.get("status") == by_status]
    items = items[-limit:] if len(items) > limit else items
    items = sorted(items, key=lambda x: x.get("updated_at", 0), reverse=True)
    return {"items": items, "total": len(items)}


def get_delivery_status(delivery_id: str) -> Optional[Dict[str, Any]]:
    """按 delivery_id 查单条投递状态，供详情页或 Bot 展示。"""
    for e in reversed(_log):
        if e.get("delivery_id") == delivery_id:
            return dict(e)
    return None
