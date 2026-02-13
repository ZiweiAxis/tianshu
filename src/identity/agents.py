# E3-S2：Agent 注册与确定性身份标识
# 注册完成时分配并落库唯一身份标识；与 Matrix 身份可关联；同一标识不重复分配
# E11-S4：读写经 storage 后端，支持 memory/sqlite/postgres

import uuid
from typing import Any, Dict, Optional

BUCKET_AGENTS = "agents"
BUCKET_DISPLAY_ID = "agents_display_id"


def _store():
    from src.storage import get_backend
    return get_backend()


def allocate_agent_id(
    matrix_id: Optional[str] = None,
    display_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    分配全局唯一、不可复用的 Agent 身份标识并落库。
    display_id：可选，人类可读/提交的标识，若提供则全局唯一。
    返回 agent_id（如 tianshu-agent-{uuid4 前 12 位}）；可与 Matrix 身份关联。
    """
    store = _store()
    if display_id is not None:
        display_id = (display_id or "").strip()
        if display_id and store.get(BUCKET_DISPLAY_ID, display_id):
            raise ValueError(f"Agent 标识已存在: {display_id}")
    while True:
        raw = uuid.uuid4().hex[:12]
        agent_id = f"tianshu-agent-{raw}"
        if not store.get(BUCKET_AGENTS, agent_id):
            break
    store.set(BUCKET_AGENTS, agent_id, {
        "agent_id": agent_id,
        "matrix_id": matrix_id,
        "display_id": display_id or None,
        "extra": extra or {},
    })
    if display_id:
        store.set(BUCKET_DISPLAY_ID, display_id, {"agent_id": agent_id})
    return agent_id


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """按 agent_id 获取 Agent 信息。"""
    v = _store().get(BUCKET_AGENTS, agent_id)
    return dict(v) if v else None


def set_agent_matrix_id(agent_id: str, matrix_id: str) -> bool:
    """关联 Agent 与 Matrix 身份。"""
    store = _store()
    rec = store.get(BUCKET_AGENTS, agent_id)
    if not rec:
        return False
    rec = dict(rec)
    rec["matrix_id"] = matrix_id
    store.set(BUCKET_AGENTS, agent_id, rec)
    return True


def agent_exists(agent_id: str) -> bool:
    """判断 agent_id 是否已分配。"""
    return _store().get(BUCKET_AGENTS, agent_id) is not None


def display_id_taken(display_id: str) -> bool:
    """判断人类提交的 Agent 标识是否已被占用（E4-S1 唯一性校验）。"""
    return _store().get(BUCKET_DISPLAY_ID, (display_id or "").strip()) is not None
