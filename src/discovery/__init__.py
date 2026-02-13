# E4-S6：Agent 发现天枢端点
# 提供可发现的端点信息（Matrix Home Server、可选 API 入口），供 Agent 解析后发起注册或上线

from src.discovery.endpoints import get_discovery_payload

__all__ = ["get_discovery_payload"]
