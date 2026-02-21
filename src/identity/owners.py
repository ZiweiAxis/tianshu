# E3-S1：人类/Owner 登记与解析
# 可登记人类身份（邮箱、工号、飞书 user_id）；按标识检索唯一匹配或候选列表；Owner 存在性可查询
# E11-S4：读写经 storage 后端

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BUCKET_OWNERS = "owners"
BUCKET_OWNERS_INDEX = "owners_index"  # key = "type:value", value = { "owner_id": "..." }


def _store():
    from storage import get_backend
    return get_backend()


def _index_key(identifier_type: str, identifier_value: str) -> str:
    return f"{identifier_type.strip().lower()}:{(identifier_value or '').strip()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def register_owner(
    identifier_type: str,
    identifier_value: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    登记人类/Owner。identifier_type 如 email、employee_id、feishu_user_id。
    若该 (type, value) 已存在则返回已有 owner_id；否则创建并返回新 owner_id。
    """
    store = _store()
    ival = (identifier_value or "").strip()
    if not ival:
        raise ValueError("identifier_value 不能为空")
    key = _index_key(identifier_type, ival)
    existing = store.get(BUCKET_OWNERS_INDEX, key)
    if existing:
        return existing["owner_id"]
    owner_id = f"owner-{uuid.uuid4().hex[:8]}"
    now = _utc_now()
    store.set(BUCKET_OWNERS, owner_id, {
        "owner_id": owner_id,
        "identifiers": {identifier_type: identifier_value},  # backward compatibility
        "identities": {identifier_type: {"value": identifier_value}},  # new structure
        "channels": [],  # new: external message channels
        "extra": extra or {},
        "created_at": now,
        "updated_at": now,
    })
    store.set(BUCKET_OWNERS_INDEX, key, {"owner_id": owner_id})
    return owner_id


def add_owner_identifier(owner_id: str, identifier_type: str, identifier_value: str) -> bool:
    """为已存在 Owner 追加标识（如同一人多个邮箱）。"""
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    key = _index_key(identifier_type, (identifier_value or "").strip())
    existing = store.get(BUCKET_OWNERS_INDEX, key)
    if existing and existing.get("owner_id") != owner_id:
        return False
    o = dict(o)
    o.setdefault("identifiers", {})[identifier_type] = identifier_value
    # Also update new identities structure
    o.setdefault("identities", {})[identifier_type] = {"value": identifier_value}
    o["updated_at"] = _utc_now()
    store.set(BUCKET_OWNERS, owner_id, o)
    store.set(BUCKET_OWNERS_INDEX, key, {"owner_id": owner_id})
    return True


def lookup_owners(
    identifier_type: Optional[str] = None,
    identifier_value: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    按标识检索。若 (identifier_type, identifier_value) 精确匹配则返回单条；
    若仅 query 则按任意标识值模糊匹配返回候选列表。
    """
    store = _store()
    if identifier_type is not None and identifier_value is not None:
        key = _index_key(identifier_type, identifier_value)
        existing = store.get(BUCKET_OWNERS_INDEX, key)
        if existing:
            o = store.get(BUCKET_OWNERS, existing["owner_id"])
            return [o] if o else []
        return []
    if query:
        q = (query or "").strip().lower()
        candidates = []
        for owner_id in store.list_keys(BUCKET_OWNERS):
            data = store.get(BUCKET_OWNERS, owner_id)
            if not data:
                continue
            # Check both old identifiers and new identities
            all_ids = {**data.get("identifiers", {}), **{k: v.get("value", v) if isinstance(v, dict) else v for k, v in (data.get("identities", {}) or {}).items()}}
            for _t, val in all_ids.items():
                if val and q in str(val).lower():
                    candidates.append(data)
                    break
        return candidates
    return [store.get(BUCKET_OWNERS, k) for k in store.list_keys(BUCKET_OWNERS) if store.get(BUCKET_OWNERS, k)]


def owner_exists(identifier_type: str, identifier_value: str) -> bool:
    """Agent 注册流程可调用：拟绑定 Owner 是否存在。"""
    key = _index_key(identifier_type, identifier_value)
    return _store().get(BUCKET_OWNERS_INDEX, key) is not None


def get_owner(owner_id: str) -> Optional[Dict[str, Any]]:
    """按 owner_id 取 Owner 信息。"""
    v = _store().get(BUCKET_OWNERS, owner_id)
    return dict(v) if v else None


# ========== 新结构：身份标识（企业内部身份）==========

def register_identity(owner_id: str, identity_type: str, identity_data: dict) -> bool:
    """
    为 Owner 注册企业内部身份标识。
    identity_type: 如 "email", "employee" 等
    identity_data: 如 {"address": "user@company.com"}, {"id": "EMP001"}
    """
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    
    # Check if this identity already exists for another owner
    if identity_type == "email" and "address" in identity_data:
        key = _index_key("email", identity_data["address"])
        existing = store.get(BUCKET_OWNERS_INDEX, key)
        if existing and existing.get("owner_id") != owner_id:
            return False
        store.set(BUCKET_OWNERS_INDEX, key, {"owner_id": owner_id})
    
    o = dict(o)
    o.setdefault("identities", {})[identity_type] = identity_data
    o["updated_at"] = _utc_now()
    store.set(BUCKET_OWNERS, owner_id, o)
    return True


def lookup_by_identity(identity_type: str, identity_value: str) -> Optional[Dict[str, Any]]:
    """
    按身份类型和值查找 Owner。
    identity_type: 如 "email", "employee"
    identity_value: 要查找的值（如邮箱地址或员工ID）
    """
    # Build the index key based on identity type
    key = _index_key(identity_type, identity_value)
    existing = _store().get(BUCKET_OWNERS_INDEX, key)
    if existing:
        return get_owner(existing["owner_id"])
    return None


# ========== 新结构：投递渠道（外部消息渠道）==========

def add_channel(owner_id: str, channel_type: str, receive_id: str) -> bool:
    """
    为 Owner 添加外部消息渠道。
    channel_type: 如 "telegram", "feishu", "email" 等
    receive_id: 渠道接收ID（如 Telegram user_id, 飞书 chat_id 等）
    """
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    
    o = dict(o)
    o.setdefault("channels", [])
    
    # Check if channel already exists
    for ch in o["channels"]:
        if ch.get("type") == channel_type:
            ch["receive_id"] = receive_id
            ch["enabled"] = True
            break
    else:
        o["channels"].append({
            "type": channel_type,
            "receive_id": receive_id,
            "enabled": True
        })
    
    o["updated_at"] = _utc_now()
    store.set(BUCKET_OWNERS, owner_id, o)
    return True


def get_channels(owner_id: str) -> List[Dict[str, Any]]:
    """获取 Owner 的所有渠道。"""
    o = _store().get(BUCKET_OWNERS, owner_id)
    if not o:
        return []
    return list(o.get("channels", []))


def get_enabled_channel(owner_id: str) -> Optional[Dict[str, Any]]:
    """获取 Owner 启用的渠道（优先返回第一个 enabled 的）。"""
    channels = get_channels(owner_id)
    for ch in channels:
        if ch.get("enabled", True):
            return ch
    return channels[0] if channels else None


def set_channel_enabled(owner_id: str, channel_type: str, enabled: bool) -> bool:
    """设置渠道是否启用。"""
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    
    o = dict(o)
    for ch in o.get("channels", []):
        if ch.get("type") == channel_type:
            ch["enabled"] = enabled
            o["updated_at"] = _utc_now()
            store.set(BUCKET_OWNERS, owner_id, o)
            return True
    return False


# ========== 旧接口兼容（E8-S3：Owner 收告警/通知需投递到其飞书会话）==========

BUCKET_OWNER_CHANNEL = "owner_channel"  # key=owner_id, value={ receive_id, receive_id_type }


def set_owner_channel(owner_id: str, receive_id: str, receive_id_type: str = "chat_id") -> bool:
    """
    登记 Owner 的飞书接收目标（chat_id 或 open_id），用于推送告警/通知。
    兼容旧接口：新结构会同步更新 channels 列表。
    """
    # Add to new channels structure
    add_channel(owner_id, "feishu", receive_id)
    # Also keep old structure for backward compatibility
    if not get_owner(owner_id):
        return False
    _store().set(BUCKET_OWNER_CHANNEL, owner_id, {"receive_id": receive_id, "receive_id_type": receive_id_type})
    return True


def get_owner_channel(owner_id: str) -> Optional[Dict[str, Any]]:
    """
    获取 Owner 的飞书接收目标，无则返回 None。
    兼容旧接口：优先从新 channels 结构获取，否则回退到旧结构。
    """
    # Try new channels first
    enabled = get_enabled_channel(owner_id)
    if enabled:
        return {
            "receive_id": enabled["receive_id"],
            "receive_id_type": enabled["type"]
        }
    # Fallback to old structure
    v = _store().get(BUCKET_OWNER_CHANNEL, owner_id)
    return dict(v) if v else None


# ========== Telegram 用户标识支持（向后兼容）==========

def register_telegram_owner(telegram_user_id: str) -> str:
    """注册 Telegram 用户对应的 Owner"""
    return register_owner("telegram_user_id", telegram_user_id)


def lookup_telegram_owner(telegram_user_id: str) -> Optional[str]:
    """查询 Telegram 用户对应的 Owner"""
    results = lookup_owners("telegram_user_id", telegram_user_id)
    return results[0]["owner_id"] if results else None


def get_or_create_telegram_owner(telegram_user_id: str) -> str:
    """获取或创建 Telegram 用户对应的 Owner"""
    existing = lookup_telegram_owner(telegram_user_id)
    if existing:
        return existing
    # Create new owner and add telegram channel
    owner_id = register_telegram_owner(telegram_user_id)
    add_channel(owner_id, "telegram", telegram_user_id)
    return owner_id


# ========== 迁移辅助函数（用于一次性迁移旧数据到新结构）==========

def migrate_telegram_to_channels(owner_id: str) -> bool:
    """
    将现有 Owner 的 telegram_user_id 标识迁移到 channels 结构。
    """
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    
    telegram_id = o.get("identifiers", {}).get("telegram_user_id")
    if not telegram_id:
        return False
    
    # Add to channels if not already there
    add_channel(owner_id, "telegram", telegram_id)
    return True
