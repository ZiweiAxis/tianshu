#!/usr/bin/env python3
"""
天枢初始化脚本
首次启动时创建系统 Owner
"""

import os
import sys

# 添加 src 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from storage import get_backend


def init_system_owners():
    """预注册系统 Owner"""
    store = get_backend()
    
    # 预注册天枢管理员
    admin_id = "admin"
    if not store.get("owners", admin_id):
        store.set("owners", admin_id, {
            "owner_id": admin_id,
            "identities": {"email": {"address": "admin@company.com"}},
            "channels": [],
            "created_at": "2026-02-21T00:00:00Z"
        })
        store.set("owners_index", "email:admin@company.com", {"owner_id": admin_id})
        print(f"✅ 已预注册管理员: {admin_id}")
    else:
        print(f"ℹ️ 管理员已存在: {admin_id}")
    
    # 预注册谛听 Owner
    diting_id = "diting"
    if not store.get("owners", diting_id):
        store.set("owners", diting_id, {
            "owner_id": diting_id,
            "identities": {"system": {"type": "diting", "name": "Diting Policy Engine"}},
            "channels": [],
            "created_at": "2026-02-21T00:00:00Z"
        })
        store.set("owners_index", "system:diting", {"owner_id": diting_id})
        print(f"✅ 已预注册谛听 Owner: {diting_id}")
    else:
        print(f"ℹ️ 谛听 Owner 已存在: {diting_id}")
    
    return True


if __name__ == "__main__":
    print("🔧 天枢初始化...")
    init_system_owners()
    print("✨ 初始化完成")
