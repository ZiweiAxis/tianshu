"""
悟空智能体服务封装模块 (MiniMax 版本)

S032: 集成 MiniMax API
S052: Skill 加载器集成
S054: LLM 集成 - Tool Call 处理
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .client import WukongClient
from .config import WukongConfig
from .skills import SkillLoader, get_loader, ExecutionResult

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
    支持 Skill 工具调用（S052）
    """

    def __init__(
        self,
        config: Optional[WukongConfig] = None,
        message_callback: Optional[Callable[[str], None]] = None,
        skill_loader: Optional[SkillLoader] = None,
        enable_skills: bool = True,
    ):
        """
        初始化悟空 Agent

        Args:
            config: 悟空配置
            message_callback: 消息回调函数（接收消息内容）
            skill_loader: SkillLoader 实例
            enable_skills: 是否启用 Skill 功能
        """
        self.config = config or WukongConfig()
        self._client = WukongClient(self.config)
        self._state = AgentState.IDLE
        self._message_callback = message_callback
        self._conversation_history: List[ConversationMessage] = []

        # Skill 加载器
        self._enable_skills = enable_skills
        self._skill_loader = skill_loader
        self._skill_contexts: Dict[str, str] = {}  # skill_name -> formatted content

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

            # 初始化 Skill 加载器
            if self._enable_skills:
                if self._skill_loader is None:
                    self._skill_loader = get_loader()

                # 加载所有 Skill 文档内容
                self._load_skill_contexts()
                logger.info(f"Loaded {len(self._skill_contexts)} skill contexts")

                # 注册重载回调
                self._skill_loader.on_reload(self._on_skills_reloaded)

            self._state = AgentState.RUNNING
            logger.info("Wukong Agent started successfully")
            return True

        except Exception as e:
            self._state = AgentState.ERROR
            logger.error(f"Failed to start agent: {e}")
            raise

    def _on_skills_reloaded(self) -> None:
        """Skill 重载回调"""
        self._load_skill_contexts()
        logger.info(f"Skills reloaded, now have {len(self._skill_contexts)} skill contexts")

    def _load_skill_contexts(self) -> None:
        """加载所有 Skill 文档内容"""
        self._skill_contexts = {}

        for ctx in self._skill_loader.get_all_contexts():
            # 格式化文档内容（不含 frontmatter）
            content = self._skill_loader.format_for_llm(ctx.skill.name, include_frontmatter=False)
            if content:
                self._skill_contexts[ctx.skill.name] = content

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
        
        # 构建消息列表
        messages = self._build_messages(message, system_prompt)
        
        # 获取相关的 Skill 上下文（文档式）
        # 注意：不发送 tools 给 API，而是让 LLM 在文本中生成调用格式，然后我们解析执行
        if self._enable_skills and self._skill_loader:
            matched_contexts = self._skill_loader.find_by_intent(message)
            if matched_contexts:
                messages = self._inject_skill_context(messages, message)
        
        # 不发送 tools，让 LLM 在文本中生成调用格式
        tools = None
        
        # 发送消息（带 Tool 调用支持）
        response = await self._send_with_tools(messages, tools)

        # 添加回复到对话历史
        self._conversation_history.append(
            ConversationMessage(role="assistant", content=response)
        )
        
        return response
    
    def _inject_skill_context(
        self,
        messages: List[Dict[str, Any]],
        user_message: str,
    ) -> List[Dict[str, Any]]:
        """
        根据用户消息查找相关 Skill 并注入上下文
        
        Args:
            messages: 消息列表
            user_message: 用户消息
            
        Returns:
            添加了 Skill 上下文的消息列表
        """
        # 查找相关的 Skill
        matched_contexts = self._skill_loader.find_by_intent(user_message)
        
        logger.info(f"[Skill] User message: {user_message}")
        logger.info(f"[Skill] Matched contexts: {[m.skill.name for m in matched_contexts]}")
        
        if not matched_contexts:
            return messages
        
        # 取最相关的 2 个 Skill
        top_contexts = matched_contexts[:2]
        
        # 构建 Skill 上下文内容
        skill_context_parts = ["## 可用 Skills\n"]
        
        for ctx in top_contexts:
            content = self._skill_contexts.get(ctx.skill.name, "")
            if content:
                skill_context_parts.append(f"### Skill: {ctx.skill.name}\n")
                skill_context_parts.append(content)
                skill_context_parts.append("\n---\n")
        
        skill_context = "\n".join(skill_context_parts)
        
        # 注入到系统消息或第一条消息中
        if messages and messages[0].get("role") == "system":
            original_content = messages[0].get("content", "")
            messages[0]["content"] = f"{original_content}\n\n{skill_context}"
        else:
            messages.insert(0, {
                "role": "system",
                "content": skill_context
            })
        
        logger.info(f"Injected context from {len(top_contexts)} skill(s): {[ctx.skill.name for ctx in top_contexts]}")
        
        return messages

    def _build_messages(
        self,
        message: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建消息列表

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            消息列表
        """
        messages = []

        # 添加系统提示
        system = system_prompt or self.config.system_prompt
        messages.append({"role": "system", "content": system})

        # 添加历史消息（最近 10 条）
        recent_history = self._conversation_history[-10:]
        for msg in recent_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # 添加当前消息
        messages.append({"role": "user", "content": message})

        return messages

    async def _send_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tool_calls: int = 5,
    ) -> str:
        """
        发送消息并处理 Tool Call（支持多轮调用）
        
        文档式 + 函数调用混合模式：
        - SKILL.md 上下文注入（让 LLM 理解任务）
        - Tool 定义（让 LLM 可以调用函数）

        Args:
            messages: 消息列表
            tools: Skill 工具定义列表
            max_tool_calls: 最大 Tool 调用次数

        Returns:
            AI 最终回复
        """
        # tools 默认为 None

        # 第一轮：发送消息获取回复
        logger.info(f"[ToolCall] Sending message with tools: {tools is not None}")
        response = await self._client.send_message_with_tools(
            messages=messages,
            tools=tools,
        )
        
        logger.info(f"[ToolCall] Got response, length: {len(response) if response else 0}")

        # 检查是否需要执行 Tool（可选功能）
        tool_calls = self._extract_tool_calls(response)

        # 最多执行 max_tool_calls 轮
        for iteration in range(max_tool_calls):
            if not tool_calls:
                break

            logger.info(f"Executing {len(tool_calls)} tool call(s), iteration {iteration + 1}")

            # 添加助手消息（包含 tool_calls）
            messages.append({
                "role": "assistant",
                "content": response if response else None,
                "tool_calls": tool_calls
            })

            # 执行每个 Tool Call
            for tool_call in tool_calls:
                result = await self._execute_tool_call(tool_call)

                # 添加工具结果消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False)
                })

            # 重新获取回复
            response = await self._client.send_message_with_tools(
                messages=messages,
                tools=tools,
            )

            # 检查是否还有 Tool Call
            tool_calls = self._extract_tool_calls(response)

        # 返回最终回复
        return response or "抱歉，我无法完成您的请求。"

    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        """
        从响应中提取 Tool Call

        Args:
            response: LLM 响应（可能是字符串或字典）

        Returns:
            Tool Call 列表
        """
        logger.info(f"[ToolCall] Extracting from response type: {type(response)}")
        logger.info(f"[ToolCall] Response content: {response[:200] if response else 'empty'}")
        
        if not response:
            return []

        # 如果是字符串，尝试提取 JSON 部分
        if isinstance(response, str):
            import re
            
            # 尝试多种格式
            
            # 格式1: <minimax:toolcall><invoke name="weather">...
            if "<minimax:toolcall>" in response:
                match = re.search(r'<invoke name="(\w+)">(.*?)</invoke>', response, re.DOTALL)
                if match:
                    tool_name = match.group(1)
                    tool_args = match.group(2)
                    params = {}
                    param_match = re.findall(r'<parameter name="(\w+)">(.*?)</parameter>', tool_args)
                    for name, value in param_match:
                        params[name] = value
                    logger.info(f"[ToolCall] Found (format1): {tool_name} with params: {params}")
                    return [{"id": "call_" + tool_name, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            
            # 格式2: 直接 <invoke name="weather">... (无 minimax:toolcall 包装)
            match = re.search(r'<invoke name="(\w+)">(.*?)</invoke>', response, re.DOTALL)
            if match:
                tool_name = match.group(1)
                tool_args = match.group(2)
                params = {}
                param_match = re.findall(r'<parameter name="(\w+)">(.*?)</parameter>', tool_args)
                for name, value in param_match:
                    params[name] = value
                logger.info(f"[ToolCall] Found (format2): {tool_name} with params: {params}")
                return [{"id": "call_" + tool_name, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            
            # 格式3: tool:weather(city="郑州")
            match = re.search(r'tool:(\w+)\((.*?)\)', response)
            if match:
                tool_name = match.group(1)
                args_str = match.group(2)
                params = {}
                for param_match in re.findall(r'(\w+)="([^"]*)"', args_str):
                    params[param_match[0]] = param_match[1]
                logger.info(f"[ToolCall] Found (format3): {tool_name} with params: {params}")
                return [{"id": "call_" + tool_name, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            
            # 格式4: [TOOL_CALL]{tool => "weather", args => {...}}[/TOOL_CALL]
            if "[TOOL_CALL]" in response:
                match = re.search(r'\[TOOL_CALL\]\s*\{tool\s*=>\s*"(\w+)"', response)
                if match:
                    tool_name = match.group(1)
                    # 提取参数
                    args_match = re.search(r'args\s*=>\s*\{([^}]+)\}', response)
                    params = {}
                    if args_match:
                        for param in re.findall(r'--(\w+)\s+"([^"]*)"', args_match.group(1)):
                            params[param[0]] = param[1]
                    logger.info(f"[ToolCall] Found (format4 TOOL_CALL): {tool_name} with params: {params}")
                    return [{"id": "call_" + tool_name, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            
            # 如果没有匹配到任何格式，记录完整响应
            logger.info(f"[ToolCall] No tool call found in response: {response[:500]}")
            
            try:
                # 尝试解析为 JSON
                response_data = json.loads(response)
            except json.JSONDecodeError:
                return []
        else:
            response_data = response

        # 检查 tool_calls 字段
        if isinstance(response_data, dict):
            return response_data.get("tool_calls", [])

        return []

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个 Tool Call

        Args:
            tool_call: Tool Call 对象

        Returns:
            执行结果
        """
        # 提取函数名和参数
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = function.get("arguments", {})

        # 解析参数
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        # 查找并执行 Skill
        skill_name = self._extract_skill_name(tool_name)

        if not skill_name:
            return {
                "success": False,
                "message": f"Unknown tool: {tool_name}"
            }

        try:
            result = self._skill_loader.execute_skill(skill_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {
                "success": False,
                "message": f"执行错误: {str(e)}",
                "error": type(e).__name__
            }

    def _get_skill_tools(self, skill_names: List[str]) -> List[Dict[str, Any]]:
        """
        获取指定 Skill 的工具定义

        Args:
            skill_names: Skill 名称列表

        Returns:
            工具定义列表
        """
        tools = []
        
        # 为每个 Skill 生成 Tool 定义
        tool_definitions = {
            "weather": {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "查询指定城市的天气信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "要查询的城市名称"
                            }
                        },
                        "required": ["city"]
                    }
                }
            }
        }
        
        for name in skill_names:
            if name in tool_definitions:
                tools.append(tool_definitions[name])
        
        return tools

    def _extract_skill_name(self, tool_name: str) -> Optional[str]:
        """
        从 Tool 名称提取 Skill 名称

        Args:
            tool_name: Tool 名称（如 "skill_weather"）

        Returns:
            Skill 名称
        """
        if tool_name.startswith("skill_"):
            return tool_name[6:]
        return tool_name

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
