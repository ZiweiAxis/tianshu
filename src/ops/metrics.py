# E6-S1 / E6-S2 / E6-S3：参与者与消息基础指标、问答式运维/Bot 查询 API、投递状态排障

from typing import Any, Dict, List, Optional

from src.identity import get_agent, get_agent_owner, get_owner_agent_ids, list_online_agents, list_relationships_for_diting
from src.identity.agent_presence import get_agent_online_status
from src.core.delivery_log import (
    query_delivery_log as _query_delivery_log,
    get_delivery_status as _get_delivery_status,
)


def get_participant_metrics() -> Dict[str, Any]:
    """
    E6-S1：返回参与者类型与数量、Agent 数、消息数（占位）、对话量等。
    可被 Bot 或运维视图消费（语义 dashboard_summary）。
    """
    rels = list_relationships_for_diting()
    agent_count = len(rels)
    unique_owners = len(set(r.get("owner_id") for r in rels if r.get("owner_id")))
    online = list_online_agents()
    return {
        "participant_count": unique_owners + agent_count,
        "agent_count": agent_count,
        "online_agent_count": len(online),
        "message_count": 0,  # 占位：需消息存储后统计
        "deliver_rate": len(online) / agent_count if agent_count else 0,
    }


def get_owner_agent_list(owner_id: str) -> Dict[str, Any]:
    """
    E8-S1：按 Owner 查询名下 Agent 列表，返回语义 agent_list（可经 Bot 或详情页展示）。
    """
    agent_ids = get_owner_agent_ids(owner_id)
    items: List[Dict[str, Any]] = []
    for aid in agent_ids:
        agent = get_agent(aid)
        status_info = get_agent_online_status(aid)
        items.append({
            "agent_id": aid,
            "owner_id": owner_id,
            "display_id": (agent or {}).get("display_id"),
            "name": (agent or {}).get("display_id") or aid,
            "status": status_info.get("status"),
            "online": status_info.get("online"),
        })
    return {"type": "agent_list", "items": items, "total": len(items)}


def query_ops(
    by_agent_id: Optional[str] = None,
    by_owner_id: Optional[str] = None,
    by_time_range: Optional[tuple] = None,
    by_collaboration: bool = False,
) -> Dict[str, Any]:
    """
    E6-S2 / E8-S1 / E10-S3：按条件查询，返回适合语义化卡片的结构。
    by_owner_id：返回该 Owner 名下 Agent 列表（语义 agent_list）。
    by_collaboration：返回协作链与异常摘要（collaboration_chains_summary）。
    """
    if by_collaboration:
        return get_collaboration_chains_summary()
    if by_owner_id:
        return get_owner_agent_list(by_owner_id)
    if by_agent_id:
        status = get_agent_online_status(by_agent_id)
        agent = get_agent(by_agent_id)
        owner_id = get_agent_owner(by_agent_id) if agent else None
        return {
            "type": "agent_detail",
            "agent_id": by_agent_id,
            "online": status.get("online"),
            "status": status.get("status"),
            "owner_id": owner_id,
            "last_seen_ts": status.get("last_seen_ts"),
        }
    metrics = get_participant_metrics()
    rels = list_relationships_for_diting()
    items = []
    for r in rels:
        aid = r.get("agent_id")
        s = get_agent_online_status(aid) if aid else {}
        items.append({
            "agent_id": aid,
            "owner_id": r.get("owner_id"),
            "status": s.get("status"),
            "online": s.get("online"),
        })
    # E6-S3：可选投递状态摘要，供排障与 Bot 展示
    delivery_summary = get_delivery_summary()
    out = {
        "type": "dashboard_summary",
        "metrics": metrics,
        "agent_list": {"items": items, "total": len(items)},
    }
    if delivery_summary:
        out["delivery_summary"] = delivery_summary
    return out


def get_delivery_summary(limit: int = 500) -> Optional[Dict[str, Any]]:
    """
    E6-S3：近期投递状态统计（delivered/failed/pending/rejected/no_reply），供运维大盘或 Bot 卡片。
    """
    result = _query_delivery_log(limit=limit)
    items = result.get("items") or []
    if not items:
        return None
    counts = {}
    for e in items:
        s = e.get("status") or "pending"
        counts[s] = counts.get(s, 0) + 1
    return {"counts": counts, "total": len(items), "sample_delivery_ids": [e.get("delivery_id") for e in items[:5]]}


def query_delivery_log(
    delivery_id: Optional[str] = None,
    by_time_range: Optional[tuple] = None,
    by_receive_id: Optional[str] = None,
    by_status: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """E6-S3：查询投递日志，供运维/Bot 排障（未触达/已触达/失败/被拒绝可区分）。"""
    return _query_delivery_log(
        delivery_id=delivery_id,
        by_time_range=by_time_range,
        by_receive_id=by_receive_id,
        by_status=by_status,
        limit=limit,
    )


def get_delivery_status(delivery_id: str) -> Optional[Dict[str, Any]]:
    """E6-S3：按 delivery_id 查单条投递状态，供详情页或 Bot 展示。"""
    return _get_delivery_status(delivery_id)


def get_collaboration_chains_summary() -> Dict[str, Any]:
    """
    E10-S3：运维可见 Agent 间协作链与异常摘要。
    返回各主从链及简单异常标注（链内存在离线 Agent 则 anomaly=True）。
    """
    rels = list_relationships_for_diting()
    seen_mains = set()
    chains = []
    for r in rels:
        main_id = r.get("agent_id")  # 每个 agent 一条；主从链以 main 为代表
        sub_ids = r.get("sub_agents") or []
        if main_id in seen_mains:
            continue
        seen_mains.add(main_id)
        agent_ids = [main_id] + sub_ids
        offline = []
        for aid in agent_ids:
            s = get_agent_online_status(aid)
            if not s.get("online"):
                offline.append(aid)
        chains.append({
            "chain_id": main_id,
            "main_agent_id": main_id,
            "agent_ids": agent_ids,
            "owner_id": r.get("owner_id"),
            "anomaly": len(offline) > 0,
            "reason": "offline_agents" if offline else None,
            "offline_agent_ids": offline,
        })
    return {
        "type": "collaboration_chains_summary",
        "chains": chains,
        "summary": {"total_chains": len(chains), "anomaly_count": sum(1 for c in chains if c.get("anomaly"))},
    }
