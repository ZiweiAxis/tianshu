# E2-S2：飞书 user_id / open_id 与天枢侧身份映射

from typing import Dict, Optional

# 内存映射：飞书 open_id -> 天枢侧显示用标识（可与 Matrix 身份或业务 ID 关联）
_feishu_to_internal: Dict[str, str] = {}
_internal_to_feishu: Dict[str, str] = {}


def get_or_create_internal_id(feishu_open_id: str) -> str:
    """飞书 open_id 对应到天枢侧唯一标识；若无则用 open_id 自身并登记。"""
    if not feishu_open_id:
        return ""
    if feishu_open_id in _feishu_to_internal:
        return _feishu_to_internal[feishu_open_id]
    internal = f"feishu:{feishu_open_id}"
    _feishu_to_internal[feishu_open_id] = internal
    _internal_to_feishu[internal] = feishu_open_id
    return internal


def get_feishu_open_id(internal_id: str) -> Optional[str]:
    """天枢侧标识 -> 飞书 open_id。"""
    return _internal_to_feishu.get(internal_id)


def set_mapping(feishu_open_id: str, internal_id: str) -> None:
    """显式设置映射（如与 Matrix 身份绑定时）。"""
    _feishu_to_internal[feishu_open_id] = internal_id
    _internal_to_feishu[internal_id] = feishu_open_id
