# 身份与关系子域（E3）
# Owner 登记与解析、Agent 确定性身份、Agent–Owner 绑定与主从链

from src.identity.owners import get_owner, owner_exists, register_owner, lookup_owners, set_owner_channel, get_owner_channel
from src.identity.agents import allocate_agent_id, get_agent, set_agent_matrix_id
from src.identity.agent_presence import (
    agent_heartbeat,
    agent_online_register,
    get_agent_online_status,
    list_online_agents,
)
from src.identity.relationships import (
    bind_agent_owner,
    register_sub_agent,
    get_agent_owner,
    get_owner_agent_ids,
    get_sub_agent_ids,
    get_main_agent_id,
    list_relationships_for_diting,
    get_agent_relationships,
    update_agent_owner,
    unbind_agent_owner,
    get_owner_change_history,
)

__all__ = [
    "agent_heartbeat",
    "agent_online_register",
    "get_agent_online_status",
    "list_online_agents",
    "get_owner",
    "register_owner",
    "lookup_owners",
    "owner_exists",
    "set_owner_channel",
    "get_owner_channel",
    "allocate_agent_id",
    "get_agent",
    "set_agent_matrix_id",
    "bind_agent_owner",
    "register_sub_agent",
    "get_agent_owner",
    "get_owner_agent_ids",
    "get_sub_agent_ids",
    "get_main_agent_id",
    "list_relationships_for_diting",
    "get_agent_relationships",
    "update_agent_owner",
    "unbind_agent_owner",
    "get_owner_change_history",
]
