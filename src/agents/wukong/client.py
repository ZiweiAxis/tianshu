"""
悟空智能体 MiniMax API 客户端
"""

import asyncio
import json
import logging
import re
from typing import Optional, Callable, AsyncIterator, Dict, Any, List
from dataclasses import dataclass
import aiohttp
import brotli

from .config import WukongConfig

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息结构"""
    role: str  # "user" or "assistant"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None


class WukongClient:
    """MiniMax API 客户端"""
    
    def __init__(self, config: Optional[WukongConfig] = None):
        """
        初始化客户端
        
        Args:
            config: 悟空配置，如果为 None 则使用默认配置
        """
        self.config = config or WukongConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_running = False
        self._message_callback: Optional[Callable[[str], None]] = None
        
    async def initialize(self) -> None:
        """初始化 MiniMax 客户端"""
        if not self.config.api_key:
            raise RuntimeError("MINIMAX_API_KEY not configured")
            
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }
        )
        self._is_running = True
        logger.info("WukongClient (MiniMax) initialized successfully")
        
    def set_message_callback(self, callback: Callable[[str], None]) -> None:
        """设置消息回调函数"""
        self._message_callback = callback
        
    def _clean_think_tags(self, text: str) -> str:
        """过滤思考标签内容"""
        if not text:
            return ""
        # 移除 think 块 (支持中文和英文标签)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()
        
    async def send_message(
        self, 
        message: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        发送消息并获取回复
        
        Args:
            message: 用户消息
            system_prompt: 系统提示词（可选）
            max_tokens: 最大 token 数（可选）
            
        Returns:
            AI 回复内容
        """
        if not self._session:
            await self.initialize()
            
        # 使用配置或默认值
        system = system_prompt or self.config.system_prompt
        max_tokens = max_tokens or self.config.max_tokens
        
        # 构建请求
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message}
            ],
            "max_tokens": max_tokens,
            "temperature": self.config.temperature,
            "stream": self.config.stream,
        }
        
        try:
            url = f"{self.config.base_url}/chat/completions"
            
            if self.config.stream:
                # 流式响应
                full_content = ""
                headers = {"Accept-Encoding": "gzip, deflate"}
                async with self._session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"API error: {resp.status} - {error_text}")
                        raise RuntimeError(f"API error: {resp.status}")
                    
                    # 处理流式响应
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if not line or not line.startswith('data:'):
                            continue
                        
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        
                        try:
                            chunk_data = json.loads(data)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_content += content
                                if self._message_callback:
                                    self._message_callback(content)
                        except json.JSONDecodeError:
                            continue
                    
                    return self._clean_think_tags(full_content)
            else:
                # 非流式响应
                async with self._session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"API error: {resp.status} - {error_text}")
                        raise RuntimeError(f"API error: {resp.status}")
                    
                    result = await resp.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if self._message_callback:
                        self._message_callback(content)
                    
                    return self._clean_think_tags(content)
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
            
    async def close(self) -> None:
        """关闭客户端"""
        if self._session:
            await self._session.close()
            self._session = None
        self._is_running = False
        logger.info("WukongClient closed")
        
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._session is not None
        
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._is_running
