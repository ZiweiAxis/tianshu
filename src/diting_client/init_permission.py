# E4-S4：注册完成后通知谛听初始化权限
# 注册完成事件含 agent_id；调用谛听「初始化权限」接口；谛听侧可据此下发默认权限

import logging
from typing import Optional

import aiohttp

from src.config import DITING_INIT_PERMISSION_URL

logger = logging.getLogger(__name__)


async def notify_agent_registered(agent_id: str, owner_id: str) -> bool:
    """
    通知谛听：Agent 已注册完成，请按 Owner 角色初始化权限。
    POST 体含 agent_id、owner_id。若未配置 DITING_INIT_PERMISSION_URL 则跳过并返回 True。
    """
    url = DITING_INIT_PERMISSION_URL or ""
    if not url.strip():
        logger.debug("未配置 DITING_INIT_PERMISSION_URL，跳过通知谛听")
        return True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"agent_id": agent_id, "owner_id": owner_id},
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status >= 200 and resp.status < 300:
                    logger.info("已通知谛听初始化权限 agent_id=%s owner_id=%s", agent_id, owner_id)
                    return True
                logger.warning("谛听初始化权限接口返回 %s: %s", resp.status, await resp.text())
                return False
    except Exception as e:
        logger.exception("通知谛听初始化权限失败: %s", e)
        return False
