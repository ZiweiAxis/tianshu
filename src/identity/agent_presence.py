# E4-S5：Agent 已有身份时上线登记与心跳
# 上线登记接口；周期性心跳；天枢维护在线状态供路由与运维查询；不重复注册

import time
from typing import Any, Dict, Optional

# agent_id -> { last_seen_ts, status }
_presence: Dict[str, Dict[str, Any]] = {}
# 默认超过此秒数未心跳视为离线
DEFAULT_OFFLINE_THRESHOLD = 120


def agent_online_register(agent_id: str, status: str = "online") -> Dict[str, Any]:
    """
    已注册 Agent 上线登记。自检已有天枢身份时调用；不重复走注册流程。
    若 agent_id 不存在则返回失败。
    """
    from src.identity.agents import agent_exists
    if not agent_exists(agent_id):
        return {"ok": False, "error": "Agent 身份不存在，请先完成注册"}
    now = time.time()
    _presence[agent_id] = {"last_seen_ts": now, "status": status or "online"}
    return {"ok": True, "agent_id": agent_id, "status": _presence[agent_id]["status"]}


def agent_heartbeat(agent_id: str, status: Optional[str] = None) -> Dict[str, Any]:
    """周期性心跳或状态上报。更新 last_seen 与可选 status。"""
    from src.identity.agents import agent_exists
    if not agent_exists(agent_id):
        return {"ok": False, "error": "Agent 身份不存在"}
    now = time.time()
    if agent_id not in _presence:
        _presence[agent_id] = {"last_seen_ts": now, "status": "online"}
    _presence[agent_id]["last_seen_ts"] = now
    if status is not None:
        _presence[agent_id]["status"] = status
    return {"ok": True, "agent_id": agent_id, "last_seen_ts": now}


def get_agent_online_status(
    agent_id: str,
    offline_threshold_seconds: float = DEFAULT_OFFLINE_THRESHOLD,
) -> Dict[str, Any]:
    """供路由与运维查询：Agent 是否在线、最后心跳时间、状态。"""
    if agent_id not in _presence:
        return {"online": False, "agent_id": agent_id, "last_seen_ts": None, "status": None}
    rec = _presence[agent_id]
    last = rec["last_seen_ts"]
    now = time.time()
    online = (now - last) <= offline_threshold_seconds if last else False
    return {
        "online": online,
        "agent_id": agent_id,
        "last_seen_ts": last,
        "status": rec.get("status"),
    }


def list_online_agents(offline_threshold_seconds: float = DEFAULT_OFFLINE_THRESHOLD) -> list:
    """返回当前在线的 agent_id 列表（供运维/路由）。"""
    now = time.time()
    return [
        aid for aid, rec in _presence.items()
        if (now - rec["last_seen_ts"]) <= offline_threshold_seconds
    ]
