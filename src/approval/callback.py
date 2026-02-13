# E5-S2：审批回调与结果回传
# 飞书卡片回调 URL 指向天枢或谛听；校验与幂等；结果回写
# E11-S4：结果经 storage 后端持久化

import time
from typing import Any, Dict, Optional

BUCKET_APPROVAL = "approval_results"


def _store():
    from src.storage import get_backend
    return get_backend()


def handle_approval_callback(
    request_id: str,
    approved: bool,
    approver_id: str,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    处理审批回调：幂等（同一 request_id 已存在则返回已有结果）、回写结果。
    """
    store = _store()
    existing = store.get(BUCKET_APPROVAL, request_id)
    if existing:
        return {"ok": True, "idempotent": True, "result": existing}
    rec = {
        "request_id": request_id,
        "approved": approved,
        "approver_id": approver_id,
        "timestamp": time.time(),
        "comment": comment or "",
    }
    store.set(BUCKET_APPROVAL, request_id, rec)
    return {"ok": True, "result": rec}


def get_approval_result(request_id: str) -> Optional[Dict[str, Any]]:
    """按 request_id 查询审批结果（供发起方与 Agent 得知）。"""
    v = _store().get(BUCKET_APPROVAL, request_id)
    return dict(v) if v else None
