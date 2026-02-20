"""
谛听权限通知模块
"""
import os
import logging
from typing import Dict, Any

import aiohttp

logger = logging.getLogger(__name__)

DITING_INIT_PERMISSION_URL = os.getenv("DITING_INIT_PERMISSION_URL", "http://diting:8080/permission/init")


async def notify_agent_registered(agent_id: str, owner_id: str) -> Dict[str, Any]:
    """
    通知谛听 Agent 已注册，初始化权限
    
    Args:
        agent_id: Agent ID
        owner_id: Owner ID
    
    Returns:
        {"ok": True, "permission_id": "xxx"} 或 {"ok": False, "error": "..."}
    """
    url = DITING_INIT_PERMISSION_URL
    payload = {
        "agent_id": agent_id,
        "owner_id": owner_id,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {"ok": True, "permission_id": data.get("permission_id", "")}
                else:
                    error_text = await response.text()
                    logger.error(f"谛听权限通知失败: {response.status} - {error_text}")
                    return {"ok": False, "error": f"HTTP {response.status}: {error_text}"}
    except aiohttp.ClientError as e:
        logger.error(f"谛听权限通知请求失败: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.error(f"谛听权限通知异常: {e}")
        return {"ok": False, "error": str(e)}
