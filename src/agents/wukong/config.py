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
    
    # API 配置 - MiniMax
    # 使用 api.minimax.chat/v1 (之前工作正常的地址)
    api_key: str = field(default_factory=lambda: os.getenv("MINIMAX_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"))
    
    # Skill 配置
    skill_enabled: bool = field(default_factory=lambda: os.getenv("SKILL_ENABLED", "true").lower() == "true")
    skill_dir: str = field(default_factory=lambda: os.getenv("SKILL_DIR", ""))
    
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
当你需要完成特定任务时，系统会提供相关的技能文档（SKILL）供你参考。
请仔细阅读 SKILL 内容，按照指引直接执行任务，无需使用特定的函数调用格式。
如果技能文档提供了具体的命令或步骤，请直接执行。"""
    
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
