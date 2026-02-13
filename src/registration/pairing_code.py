# E4-S3：配对码与人类确认
# 天枢生成人类可读配对码与过期时间；人类输入配对码后校验通过则完成注册并建立 Agent–Owner 绑定

import random
import string
import time
from typing import Any, Dict, Optional

from src.identity import allocate_agent_id, bind_agent_owner, get_owner

# pairing_code -> { owner_id, expires_at_ts }
_pending: Dict[str, Dict[str, Any]] = {}
# 默认有效期（秒）
DEFAULT_TTL = 600  # 10 分钟


def _make_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def create_pairing_code(
    owner_id: str,
    ttl_seconds: int = DEFAULT_TTL,
    agent_display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    为指定 Owner 生成配对码并落库。
    返回 pairing_code、expires_at（ISO 或时间戳）、payload 供推送 registration_confirm 语义。
    """
    if not get_owner(owner_id):
        return {"ok": False, "error": "Owner 不存在"}
    code = _make_code(6)
    while code in _pending:
        code = _make_code(6)
    expires_at = time.time() + ttl_seconds
    _pending[code] = {
        "owner_id": owner_id,
        "expires_at": expires_at,
        "agent_display_name": agent_display_name,
    }
    return {
        "ok": True,
        "pairing_code": code,
        "expires_at": expires_at,
        "expires_at_seconds": int(expires_at),
        "registration_confirm_payload": {
            "pairing_code": code,
            "agent_display_name": agent_display_name or "Agent",
            "expire_at": int(expires_at),
        },
    }


def submit_pairing_code(
    pairing_code: str,
    agent_display_id: Optional[str] = None,
    notify_diting: bool = False,
) -> Dict[str, Any]:
    """
    人类输入配对码后调用：校验通过则分配 agent_id、建立 Agent–Owner 绑定并清除待办。
    """
    code = (pairing_code or "").strip().upper()
    if not code:
        return {"ok": False, "error": "配对码不能为空"}
    if code not in _pending:
        return {"ok": False, "error": "配对码无效或已过期"}
    rec = _pending[code]
    if time.time() > rec["expires_at"]:
        del _pending[code]
        return {"ok": False, "error": "配对码已过期"}
    owner_id = rec["owner_id"]
    try:
        agent_id = allocate_agent_id(display_id=agent_display_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not bind_agent_owner(agent_id, owner_id):
        del _pending[code]
        return {"ok": False, "error": "绑定 Owner 失败"}
    del _pending[code]
    if notify_diting:
        from src.registration.human_initiated import _notify_diting_init_permission
        _notify_diting_init_permission(agent_id, owner_id)
    return {"ok": True, "agent_id": agent_id, "owner_id": owner_id}
