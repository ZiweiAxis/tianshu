# E3-S3：Agent–Owner 绑定与主从链
# Agent 注册时建立与 Owner 的绑定；主 Agent 可声明 Sub-agent 主从关系；关系数据可被谛听拉取
# E11-S4：读写经 storage 后端

from typing import Any, Dict, List, Optional

BUCKET_AGENT_OWNER = "rel_agent_owner"   # key=agent_id, value={owner_id}
BUCKET_MAIN_SUB = "rel_main_sub"         # key=main_id, value={sub_ids: [...]}
BUCKET_SUB_MAIN = "rel_sub_main"         # key=sub_id, value={main_id}


def _store():
    from src.storage import get_backend
    return get_backend()


def bind_agent_owner(agent_id: str, owner_id: str) -> bool:
    """Agent 注册时建立与 Owner 的绑定并落库。"""
    from src.identity.agents import agent_exists
    from src.identity.owners import get_owner

    if not agent_exists(agent_id) or not get_owner(owner_id):
        return False
    _store().set(BUCKET_AGENT_OWNER, agent_id, {"owner_id": owner_id})
    return True


def get_agent_owner(agent_id: str) -> Optional[str]:
    """返回 Agent 绑定的 owner_id。"""
    v = _store().get(BUCKET_AGENT_OWNER, agent_id)
    return v.get("owner_id") if v else None


def get_owner_agent_ids(owner_id: str) -> List[str]:
    """某 Owner 名下所有 Agent（供 E8-S1、谛听拉取）。"""
    store = _store()
    out = []
    for aid in store.list_keys(BUCKET_AGENT_OWNER):
        v = store.get(BUCKET_AGENT_OWNER, aid)
        if v and v.get("owner_id") == owner_id:
            out.append(aid)
    return out


def register_sub_agent(main_agent_id: str, sub_agent_id: str) -> bool:
    """E9-S1：主 Agent 登记 Sub-agent 主从关系并落库；可选通知谛听。"""
    from src.identity.agents import agent_exists

    if not agent_exists(main_agent_id) or not agent_exists(sub_agent_id):
        return False
    store = _store()
    rec = store.get(BUCKET_MAIN_SUB, main_agent_id) or {"sub_ids": []}
    sub_ids = list(rec.get("sub_ids") or [])
    if sub_agent_id not in sub_ids:
        sub_ids.append(sub_agent_id)
    store.set(BUCKET_MAIN_SUB, main_agent_id, {"sub_ids": sub_ids})
    store.set(BUCKET_SUB_MAIN, sub_agent_id, {"main_id": main_agent_id})
    _notify_diting_sub_agent(main_agent_id, sub_agent_id)
    return True


def _notify_diting_sub_agent(main_agent_id: str, sub_agent_id: str) -> None:
    """E9-S1：可选通知谛听 Sub-agent 登记（若配置了 DITING_SUB_AGENT_REGISTER_URL）。"""
    import os
    url = os.getenv("DITING_SUB_AGENT_REGISTER_URL")
    if not url:
        return
    try:
        import urllib.request
        import json
        req = urllib.request.Request(url, data=json.dumps({"main_agent_id": main_agent_id, "sub_agent_id": sub_agent_id}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def get_sub_agent_ids(main_agent_id: str) -> List[str]:
    """某主 Agent 下所有 Sub-agent。"""
    v = _store().get(BUCKET_MAIN_SUB, main_agent_id)
    return list(v.get("sub_ids", [])) if v else []


def get_main_agent_id(sub_agent_id: str) -> Optional[str]:
    """Sub-agent 所属主 Agent。"""
    v = _store().get(BUCKET_SUB_MAIN, sub_agent_id)
    return v.get("main_id") if v else None


def list_relationships_for_diting() -> List[Dict[str, Any]]:
    """关系数据可被谛听拉取：返回 Agent–Owner 及主从链摘要。"""
    store = _store()
    out = []
    for agent_id in store.list_keys(BUCKET_AGENT_OWNER):
        v = store.get(BUCKET_AGENT_OWNER, agent_id)
        if v:
            out.append({
                "agent_id": agent_id,
                "owner_id": v.get("owner_id"),
                "sub_agents": get_sub_agent_ids(agent_id),
            })
    return out


def get_agent_relationships(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    E10-S2：按 agent_id 查协作关系与主从链，供运维/谛听审计与排障。
    返回：owner_id、main_agent_id（若为 Sub）、sub_agent_ids（若为主）、collaboration_chain（该 Agent 所在主从链的 agent_id 列表）。
    """
    from src.identity.agents import get_agent
    if not get_agent(agent_id):
        return None
    owner_id = get_agent_owner(agent_id)
    main_id = get_main_agent_id(agent_id)
    sub_ids = get_sub_agent_ids(agent_id)
    # 协作链：若为 Sub 则 [main, self, ...main 的其它 sub]；若为主则 [self, sub1, sub2, ...]
    if main_id:
        chain = [main_id, agent_id] + [s for s in get_sub_agent_ids(main_id) if s != agent_id]
    else:
        chain = [agent_id] + sub_ids
    return {
        "agent_id": agent_id,
        "owner_id": owner_id,
        "main_agent_id": main_id,
        "sub_agent_ids": sub_ids,
        "collaboration_chain": chain,
    }


# E8-S2：Owner 变更、解绑（落库 + 变更历史可查）
BUCKET_OWNER_HISTORY = "owner_change_history"  # key=agent_id:seq, value={ agent_id, from_owner, to_owner, at }


def _append_owner_history(agent_id: str, from_owner: Optional[str], to_owner: Optional[str]) -> None:
    import time
    at = time.time()
    store = _store()
    store.set(BUCKET_OWNER_HISTORY, f"{agent_id}:{at}", {
        "agent_id": agent_id,
        "from_owner": from_owner,
        "to_owner": to_owner,
        "at": at,
    })


def update_agent_owner(agent_id: str, new_owner_id: str) -> bool:
    """E8-S2：变更 Agent 的 Owner（转移），落库并记录变更历史。"""
    from src.identity.agents import agent_exists
    from src.identity.owners import get_owner
    if not agent_exists(agent_id) or not get_owner(new_owner_id):
        return False
    old = get_agent_owner(agent_id)
    _store().set(BUCKET_AGENT_OWNER, agent_id, {"owner_id": new_owner_id})
    _append_owner_history(agent_id, old, new_owner_id)
    return True


def unbind_agent_owner(agent_id: str) -> bool:
    """E8-S2：解绑 Agent 与 Owner（移除绑定），落库并记录变更历史。"""
    from src.identity.agents import agent_exists
    if not agent_exists(agent_id):
        return False
    old = get_agent_owner(agent_id)
    if not old:
        return True
    _store().delete(BUCKET_AGENT_OWNER, agent_id)
    _append_owner_history(agent_id, old, None)
    return True


def get_owner_change_history(agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """E8-S2：查询某 Agent 的 Owner 变更历史，供审计。"""
    store = _store()
    keys = sorted(store.list_keys(BUCKET_OWNER_HISTORY, prefix=agent_id + ":"), reverse=True)[:limit]
    out = []
    for k in keys:
        v = store.get(BUCKET_OWNER_HISTORY, k)
        if v:
            out.append(v)
    return out
