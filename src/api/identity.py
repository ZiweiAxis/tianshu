# E7-S2 / E10-S2 / E8-S2：身份与关系、协作链、变更历史 API

from src.identity import (
    list_relationships_for_diting,
    get_agent_relationships,
    get_owner_change_history,
)


def get_identity_relationships():
    """返回身份与关系数据（Owner、主从 Agent 等），与存储一致。谛听可按需或定时同步。"""
    return list_relationships_for_diting()


def get_agent_relationships(agent_id: str):
    """E10-S2：按 agent_id 查协作关系与主从链，供运维/谛听审计与排障。"""
    from src.identity.relationships import get_agent_relationships as _get_rel
    return _get_rel(agent_id)


def get_owner_change_history(agent_id: str, limit: int = 50):
    """E8-S2：查询某 Agent 的 Owner 变更历史，供审计。"""
    from src.identity.relationships import get_owner_change_history as _get_hist
    return _get_hist(agent_id, limit)
