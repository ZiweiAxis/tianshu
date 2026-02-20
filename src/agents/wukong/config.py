"""
悟空智能体配置模块 (MiniMax 版本)

S032: 集成 MiniMax API
"""

import os
from typing import List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class WukongConfig:
    """悟空 Agent 配置"""
    
    # API 配置 - 支持 MiniMax
    api_key: str = field(default_factory=lambda: os.getenv("MINIMAX_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"))
    
    # 天枢/太白配置
    tianshu_url: str = field(default_factory=lambda: os.getenv("TIANSHU_URL", "http://localhost:8082"))
    tianshu_token: Optional[str] = field(default_factory=lambda: os.getenv("TIANSHU_TOKEN", None))
    taibai_url: str = field(default_factory=lambda: os.getenv("TAIBAI_URL", "http://localhost:8081"))
    
    # 模型配置 - MiniMax 模型
    model: str = "MiniMax-M2.5"
    max_tokens: int = 4096
    temperature: float = 1.0
    
    # 工具配置
    allowed_tools: List[str] = field(default_factory=lambda: [
        "read",
        "write", 
        "exec",
        "browser",
        "web_search",
        "web_fetch",
    ])
    
    # 权限模式
    permission_mode: str = "auto"  # auto, manual, deny
    
    # 系统提示词
    system_prompt: str = """你是悟空，一个强大的 AI 智能体助手。
你可以通过各种工具来完成复杂任务。
请始终遵循用户的指示，并尽可能提供帮助。"""
    
    # 流式输出
    stream: bool = True
    
    # 消息通道配置
    enable_message_channel: bool = True
    stream_output: bool = True  # 是否启用流式输出


# 默认配置实例
default_config = WukongConfig()


def load_config(**kwargs) -> WukongConfig:
    """加载自定义配置"""
    config = WukongConfig()
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return config
