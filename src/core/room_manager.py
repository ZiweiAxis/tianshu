# E2-S2：飞书会话/群 chat_id 与 Matrix room_id 映射与生命周期

from typing import Dict, List, Optional

from src.config import USE_PRIVATE_ROOM, SHARED_ROOM_ID

# 飞书 chat_id -> Matrix room_id
_chat_to_room: Dict[str, str] = {}
# Matrix room_id -> 飞书 chat_id 列表（共享房间时多 chat 对应同一 room）
_room_to_chats: Dict[str, List[str]] = {}


def get_matrix_room_id(feishu_chat_id: str) -> Optional[str]:
    """根据飞书 chat_id 获取已映射的 Matrix room_id。"""
    if USE_PRIVATE_ROOM:
        return _chat_to_room.get(feishu_chat_id)
    return SHARED_ROOM_ID if SHARED_ROOM_ID else _chat_to_room.get(feishu_chat_id)


def set_room_mapping(feishu_chat_id: str, matrix_room_id: str) -> None:
    """登记飞书会话/群与 Matrix Room 的映射。"""
    _chat_to_room[feishu_chat_id] = matrix_room_id
    _room_to_chats.setdefault(matrix_room_id, []).append(feishu_chat_id)
    # 去重保持顺序
    _room_to_chats[matrix_room_id] = list(dict.fromkeys(_room_to_chats[matrix_room_id]))


def get_feishu_chat_id(matrix_room_id: str) -> Optional[str]:
    """根据 Matrix room_id 取第一个飞书 chat_id（兼容单聊）。"""
    chats = _room_to_chats.get(matrix_room_id)
    return chats[0] if chats else None


def get_feishu_chat_ids(matrix_room_id: str) -> List[str]:
    """根据 Matrix room_id 获取全部飞书 chat_id 列表（共享房间时向多群转发）。"""
    return list(_room_to_chats.get(matrix_room_id) or [])


def forget_room(matrix_room_id: str) -> None:
    """移除 Room 映射（如退群时）。"""
    for chat_id in _room_to_chats.pop(matrix_room_id, []):
        _chat_to_room.pop(chat_id, None)
