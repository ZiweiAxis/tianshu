# E4-S1：人发起注册主 Agent
# 提交 Agent 标识与 Owner 信息；校验人类身份可认证、Agent 标识全局唯一；落库并绑定；可选通知谛听

from typing import Any, Dict, Optional

from src.identity import (
    allocate_agent_id,
    bind_agent_owner,
    lookup_owners,
    register_owner,
)


def register_agent_by_human(
    owner_identifier_type: str,
    owner_identifier_value: str,
    agent_display_id: Optional[str] = None,
    ensure_owner_registered: bool = True,
    notify_diting: bool = False,
) -> Dict[str, Any]:
    """
    人发起注册主 Agent：绑定本人或指定负责人，分配确定性身份并落库。
    - owner_identifier_type / owner_identifier_value：Owner 标识（如 email、feishu_user_id）；若 ensure_owner_registered 为 True 且不存在则先登记。
    - agent_display_id：可选，人类提交的 Agent 标识，须全局唯一。
    返回 {"ok": True, "agent_id": "...", "owner_id": "..."} 或 {"ok": False, "error": "..."}。
    """
    # 1) Owner 解析：唯一匹配或先登记
    owners = lookup_owners(owner_identifier_type, owner_identifier_value)
    if not owners:
        if not ensure_owner_registered:
            return {"ok": False, "error": "Owner 不存在，请先登记"}
        owner_id = register_owner(owner_identifier_type, owner_identifier_value)
    else:
        owner_id = owners[0]["owner_id"]
    # 2) Agent 标识全局唯一
    from src.identity.agents import display_id_taken

    if agent_display_id and display_id_taken(agent_display_id):
        return {"ok": False, "error": f"Agent 标识已存在: {agent_display_id}"}
    # 3) 分配 agent_id 并绑定 Owner
    try:
        agent_id = allocate_agent_id(display_id=agent_display_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not bind_agent_owner(agent_id, owner_id):
        return {"ok": False, "error": "绑定 Owner 失败"}
    # 4) 可选通知谛听（E4-S4 占位）
    if notify_diting:
        _notify_diting_init_permission(agent_id, owner_id)
    return {"ok": True, "agent_id": agent_id, "owner_id": owner_id}


def _notify_diting_init_permission(agent_id: str, owner_id: str) -> None:
    """E4-S4：注册完成后通知谛听初始化权限；I-018：并调用谛听链上 DID 注册。"""
    import asyncio
    from src.diting_client.init_permission import notify_agent_registered
    from src.diting_client.chain_did import register_did_on_chain

    async def _notify_and_chain() -> None:
        await notify_agent_registered(agent_id, owner_id)
        await register_did_on_chain(agent_id, owner_id)

    try:
        asyncio.run(_notify_and_chain())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(notify_agent_registered(agent_id, owner_id))
        loop.create_task(register_did_on_chain(agent_id, owner_id))
