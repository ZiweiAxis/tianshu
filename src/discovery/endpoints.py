# E4-S6：天枢端点发现
# Agent 可据此解析 Home Server 或 API 入口；与 .well-known / federation 约定一致

import os
from typing import Any, Dict, Optional

from src.config import MATRIX_HOMESERVER

# 可选：天枢 HTTP API 根地址（若部署时暴露）
TIANSHU_API_BASE = os.getenv("TIANSHU_API_BASE")


def get_discovery_payload(api_base: Optional[str] = None) -> Dict[str, Any]:
    """
    返回 Agent 可发现的端点信息。
    部署时可通过 GET /.well-known/tianshu-matrix 或 GET /api/v1/discovery 返回此 JSON。
    """
    base = api_base or TIANSHU_API_BASE
    payload = {
        "matrix_homeserver": (MATRIX_HOMESERVER or "").rstrip("/"),
        "version": "1.0",
    }
    if base:
        payload["api_base"] = base.rstrip("/")
    return payload
