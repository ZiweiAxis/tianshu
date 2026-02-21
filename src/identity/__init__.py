# 身份与关系子域（E3）
# Owner 登记与解析、Agent 确定性身份、Agent–Owner 绑定与主从链

from identity.owners import (
    get_owner,
    owner_exists,
    register_owner,
    lookup_owners,
    set_owner_channel,
    get_owner_channel,
    # 新增：身份管理
    register_identity,
    lookup_by_identity,
    # 新增：渠道管理
    add_channel,
    get_channels,
    get_enabled_channel,
    set_channel_enabled,
    # 新增：迁移辅助
    migrate_telegram_to_channels,
    # Telegram 兼容
    get_or_create_telegram_owner,
)
from identity.agents import allocate_agent_id, get_agent, set_agent_matrix_id
from identity.agent_presence import (
    agent_heartbeat,
    agent_online_register,
    get_agent_online_status,
    list_online_agents,
)
from identity.relationships import (
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
    # Owner 管理
    "get_owner",
    "register_owner",
    "lookup_owners",
    "owner_exists",
    "set_owner_channel",
    "get_owner_channel",
    # 新增：身份管理（企业内部身份）
    "register_identity",
    "lookup_by_identity",
    # 新增：渠道管理（外部消息渠道）
    "add_channel",
    "get_channels",
    "get_enabled_channel",
    "set_channel_enabled",
    # 新增：迁移辅助
    "migrate_telegram_to_channels",
    # 新增：Telegram 兼容
    "get_or_create_telegram_owner",
    # Agent 管理
    "allocate_agent_id",
    "get_agent",
    "set_agent_matrix_id",
    # 关系管理
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
