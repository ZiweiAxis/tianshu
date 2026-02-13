# E10-S1：Agent 收件 Room 映射
# 已注册 Agent 对应一个 Matrix Room，发往该 Agent 的消息发到此 Room；Agent 加入该 Room 即可收消息

from typing import Dict, Optional

# agent_id -> matrix_room_id
_agent_room: Dict[str, str] = {}


def get_room_for_agent(agent_id: str) -> Optional[str]:
    """获取 Agent 的收件 Matrix Room ID；无则返回 None。"""
    return _agent_room.get(agent_id)


def set_room_for_agent(agent_id: str, matrix_room_id: str) -> None:
    """登记 Agent 与 Matrix Room 的映射。"""
    _agent_room[agent_id] = matrix_room_id


async def ensure_room_for_agent(agent_id: str, matrix_client) -> Optional[str]:
    """
    确保该 Agent 有收件 Room；若尚无则创建并登记。
    返回 room_id，失败返回 None。
    """
    room_id = get_room_for_agent(agent_id)
    if room_id:
        return room_id
    if not matrix_client or not hasattr(matrix_client, "create_room"):
        return None
    room_id = await matrix_client.create_room(name=f"agent-{agent_id[:24]}")
    if room_id:
        set_room_for_agent(agent_id, room_id)
    return room_id
