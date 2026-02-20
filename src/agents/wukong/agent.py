"""
悟空智能体服务封装模块 (MiniMax 版本)

S032: 集成 MiniMax API
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .client import WukongClient
from .config import WukongConfig

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent 状态"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ConversationMessage:
    """对话消息"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    metadata: Dict[str, Any] = field(default_factory=dict)


class WukongAgent:
    """
    悟空智能体服务封装 (MiniMax 版本)
    
    提供统一的 Agent 服务接口，支持启动、停止、消息发送等功能。
    """
    
    def __init__(
        self,
        config: Optional[WukongConfig] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        初始化悟空 Agent
        
        Args:
            config: 悟空配置
            message_callback: 消息回调函数（接收消息内容）
        """
        self.config = config or WukongConfig()
        self._client = WukongClient(self.config)
        self._state = AgentState.IDLE
        self._message_callback = message_callback
        self._conversation_history: List[ConversationMessage] = []
        
    async def start(self) -> bool:
        """
        启动 Agent
        
        Returns:
            是否启动成功
        """
        if self._state == AgentState.RUNNING:
            logger.warning("Agent is already running")
            return True
            
        try:
            self._state = AgentState.STARTING
            logger.info("Starting Wukong Agent (MiniMax)...")
            
            # 初始化客户端
            await self._client.initialize()
            
            # 设置消息回调
            if self._message_callback:
                self._client.set_message_callback(self._message_callback)
            
            self._state = AgentState.RUNNING
            logger.info("Wukong Agent started successfully")
            return True
            
        except Exception as e:
            self._state = AgentState.ERROR
            logger.error(f"Failed to start agent: {e}")
            raise
            
    async def stop(self) -> bool:
        """
        停止 Agent
        
        Returns:
            是否停止成功
        """
        if self._state == AgentState.IDLE:
            logger.warning("Agent is not running")
            return True
            
        try:
            self._state = AgentState.STOPPING
            logger.info("Stopping Wukong Agent...")
                
            # 关闭客户端
            await self._client.close()
            
            self._state = AgentState.IDLE
            logger.info("Wukong Agent stopped successfully")
            return True
            
        except Exception as e:
            self._state = AgentState.ERROR
            logger.error(f"Failed to stop agent: {e}")
            raise
            
    async def send_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        发送消息
        
        Args:
            message: 用户消息
            system_prompt: 系统提示词（可选）
            
        Returns:
            AI 回复
        """
        if self._state != AgentState.RUNNING:
            raise RuntimeError("Agent is not running")
            
        # 添加到对话历史
        self._conversation_history.append(
            ConversationMessage(role="user", content=message)
        )
        
        try:
            # 发送消息
            response = await self._client.send_message(
                message=message,
                system_prompt=system_prompt,
            )
            
            # 添加回复到对话历史
            self._conversation_history.append(
                ConversationMessage(role="assistant", content=response)
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
            
    def on_message(self, callback: Callable[[str], None]) -> None:
        """
        设置消息回调
        
        Args:
            callback: 回调函数，接收消息内容
        """
        self._message_callback = callback
        if self._client.is_initialized:
            self._client.set_message_callback(callback)
            
    def get_history(self) -> List[ConversationMessage]:
        """获取对话历史"""
        return self._conversation_history.copy()
        
    async def clear_history(self, chat_id: int = None) -> None:
        """清空对话历史"""
        self._conversation_history.clear()
        
    @property
    def state(self) -> AgentState:
        """获取当前状态"""
        return self._state
        
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._state == AgentState.RUNNING


class WukongAgentFactory:
    """悟空 Agent 工厂类"""
    
    @staticmethod
    def create(config: Optional[WukongConfig] = None) -> WukongAgent:
        """
        创建悟空 Agent
        
        Args:
            config: 配置
            
        Returns:
            WukongAgent 实例
        """
        return WukongAgent(config=config)
        
    @staticmethod
    async def create_and_start(
        config: Optional[WukongConfig] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> WukongAgent:
        """
        创建并启动悟空 Agent
        
        Args:
            config: 配置
            message_callback: 消息回调
            
        Returns:
            已启动的 WukongAgent 实例
        """
        agent = WukongAgent(config=config, message_callback=message_callback)
        await agent.start()
        return agent
