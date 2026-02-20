"""
悟空 Bot 处理模块

S030: 接入天枢消息系统
- 接收用户消息
- 调用悟空 Agent
- 返回结果

环境变量：
- TELEGRAM_WUKONG_BOT_TOKEN: Telegram Bot Token
- HTTP_PROXY / HTTPS_PROXY: 代理配置
- MINIMAX_API_KEY: MiniMax API Key (S032)
"""

import asyncio
import logging
import os
import signal
import sys
from typing import List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 导入 Telegram 客户端
from telegram_client import TelegramClient, TelegramUpdate, TelegramMessage

# 导入悟空 Agent
from agents.wukong.agent import WukongAgent
from agents.wukong.config import WukongConfig

# 导入身份服务 (S035: owner_id 路由)
from src.identity.owners import get_or_create_telegram_owner


class WukongBot:
    """悟空 Bot 主程序"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.agent: Optional[WukongAgent] = None
        self.running = False
        
    def load_config(self):
        """加载配置"""
        # Telegram Bot Token
        self.token = os.getenv("TELEGRAM_WUKONG_BOT_TOKEN")
        if not self.token:
            logger.error("请设置 TELEGRAM_WUKONG_BOT_TOKEN 环境变量")
            sys.exit(1)
        
        # MiniMax API Key (S032)
        self.minimax_api_key = os.getenv("MINIMAX_API_KEY")
        if not self.minimax_api_key:
            logger.warning("未设置 MINIMAX_API_KEY，将使用默认配置")
        
        # 代理配置
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")
        
        logger.info("配置加载完成")
        
    async def initialize(self):
        """初始化 Bot 和 Agent"""
        self.load_config()
        
        # 创建 Telegram 客户端
        self.client = TelegramClient(token=self.token)
        
        # 创建悟空 Agent (S032: 使用 MiniMax API)
        config = WukongConfig()
        if self.minimax_api_key:
            config.api_key = self.minimax_api_key
        # 禁用消息通道（通过 Telegram 直接回复）
        config.enable_message_channel = False
        self.agent = WukongAgent(config=config)
        
        # 启动 Agent
        await self.agent.start()
        
        # 获取 Bot 信息
        bot_info = await self.client.get_me()
        if bot_info:
            logger.info(f"Bot 启动成功: @{bot_info.get('username')} ({bot_info.get('first_name')})")
        else:
            logger.error("无法获取 Bot 信息，请检查 Token")
            await self.client.close()
            sys.exit(1)
        
    async def handle_message(self, update: TelegramUpdate):
        """
        处理用户消息
        
        Args:
            update: Telegram Update 对象
        """
        # 记录接收到的消息
        logger.info("=" * 50)
        logger.info(f"📥 收到消息更新: update_id={update.update_id}")
        
        try:
            message = update.message
            if not message:
                logger.warning("消息为空，跳过处理")
                return
            
            # 提取消息内容
            chat_id = message.chat_id
            message_id = message.message_id
            user_id = message.user_id
            username = message.username or message.first_name or "Unknown"
            
            # 发送 typing 状态
            await self.client.send_chat_action(chat_id, "typing")
            
            # 获取文本内容（支持文本和图片 caption）
            text = message.text or message.caption or ""
            
            logger.info(f"👤 用户: {username} (id={user_id})")
            logger.info(f"💬 群组: {message.chat_id} (type={message.chat_type})")
            logger.info(f"📝 内容: {text[:100]}{'...' if len(text) > 100 else ''}")
            
            # 空消息处理
            if not text:
                logger.info("消息内容为空，跳过")
                return
            
            # ==================== 命令处理 ====================
            if message.is_command:
                await self._handle_command(update, message)
                return
            
            # ==================== 普通消息处理 ====================
            # 获取或创建 owner_id (S035)
            telegram_user_id = str(user_id)
            owner_id = get_or_create_telegram_owner(telegram_user_id)
            logger.info(f"🔑 owner_id: {owner_id}")
            
            # 调用悟空 Agent 处理 (S035: 传递 owner_id)
            response = await self._call_agent(text, chat_id, owner_id)
            
            # 发送回复 (带错误处理)
            try:
                message_id_sent = await self.client.send_message(
                    chat_id=chat_id,
                    text=response,
                    reply_to_message_id=message_id,
                )
                if message_id_sent:
                    logger.info(f"✅ 消息发送成功: msg_id={message_id_sent}")
                else:
                    logger.warning(f"⚠️ 消息发送返回失败")
            except Exception as send_error:
                logger.error(f"❌ 发送回复失败: {send_error}")
                # 尝试不带回复引用再发一次
                try:
                    await self.client.send_message(
                        chat_id=chat_id,
                        text=response,
                    )
                    logger.info("✅ 重发消息成功（无引用）")
                except Exception as retry_error:
                    logger.error(f"❌ 重发消息也失败: {retry_error}")
            
            logger.info(f"✅ 消息处理完成")
            
        except Exception as e:
            logger.exception(f"❌ 处理消息失败: {e}")
            # 尝试发送错误消息给用户
            try:
                if update.message:
                    await self.client.send_message(
                        chat_id=message.chat_id,
                        text="⚠️ 处理消息时发生错误，请稍后重试。",
                    )
            except Exception as send_error:
                logger.error(f"发送错误消息也失败了: {send_error}")
    
    async def _handle_command(self, update: TelegramUpdate, message: TelegramMessage):
        """
        处理命令消息
        
        Args:
            update: Telegram Update 对象
            message: 解析后的消息对象
        """
        command = message.command
        args = message.command_args or []
        chat_id = message.chat_id
        message_id = message.message_id
        
        logger.info(f"🔧 收到命令: /{command} {' '.join(args) if args else ''}")
        
        # 命令处理映射
        commands = {
            "start": self._cmd_start,
            "help": self._cmd_help,
            "clear": self._cmd_clear,
            "status": self._cmd_status,
        }
        
        handler = commands.get(command)
        if handler:
            try:
                await handler(update, args)
                logger.info(f"✅ 命令 /{command} 处理完成")
            except Exception as e:
                logger.exception(f"❌ 命令 /{command} 执行失败: {e}")
                await self.client.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ 命令执行失败: {str(e)[:100]}",
                )
        else:
            logger.warning(f"⚠️ 未知命令: /{command}")
            await self.client.send_message(
                chat_id=chat_id,
                text=f"❓ 未知命令 /{command}\n发送 /help 查看可用命令",
            )
    
    async def _cmd_start(self, update: TelegramUpdate, args: List[str]):
        """处理 /start 命令"""
        message = update.message
        chat_id = message.chat_id
        username = message.username or message.first_name or "你好"
        
        welcome_text = f"""
👋 你好，{username}！

我是 **悟空**，一个 AI 助手。

我可以帮你：
- 回答问题
- 协助完成各种任务
- 聊天解闷

使用方法：
- 直接发送消息问我问题
- 发送 /help 查看所有命令
- 发送 /clear 清除对话历史

开始使用吧！🎉
"""
        await self.client.send_message(
            chat_id=chat_id,
            text=welcome_text.strip(),
        )
    
    async def _cmd_help(self, update: TelegramUpdate, args: List[str]):
        """处理 /help 命令"""
        message = update.message
        chat_id = message.chat_id
        
        help_text = """
📖 **悟空命令帮助**

/start - 重新开始对话
/help - 显示帮助信息
/clear - 清除对话历史
/status - 查看状态

**其他功能：**
- 直接发送消息与我对话
- 支持图片描述（发送图片 + caption）
- 回复我的消息继续对话

有任何问题随时问我！ 😊
"""
        await self.client.send_message(
            chat_id=chat_id,
            text=help_text.strip(),
        )
    
    async def _cmd_clear(self, update: TelegramUpdate, args: List[str]):
        """处理 /clear 命令 - 清除对话历史"""
        message = update.message
        chat_id = message.chat_id
        
        try:
            # 清除对话历史
            if self.agent and hasattr(self.agent, 'clear_history'):
                await self.agent.clear_history(chat_id)
            
            await self.client.send_message(
                chat_id=chat_id,
                text="🗑️ 对话历史已清除",
            )
            logger.info(f"🗑️ 用户 {chat_id} 清除了对话历史")
        except Exception as e:
            logger.error(f"清除历史失败: {e}")
            await self.client.send_message(
                chat_id=chat_id,
                text="⚠️ 清除历史失败",
            )
    
    async def _cmd_status(self, update: TelegramUpdate, args: List[str]):
        """处理 /status 命令 - 查看状态"""
        message = update.message
        chat_id = message.chat_id
        
        # 获取 Bot 信息
        bot_info = await self.client.get_me()
        bot_name = bot_info.get('first_name', '悟空') if bot_info else '悟空'
        
        status_text = f"""
🤖 **{bot_name} 状态**

- 状态: ✅ 运行正常
- 平台: Telegram
- 版本: S031

当前会话: {chat_id}
"""
        await self.client.send_message(
            chat_id=chat_id,
            text=status_text.strip(),
        )
    
    async def _call_agent(self, text: str, chat_id: int, owner_id: str = None) -> str:
        """
        调用悟空 Agent 处理消息
        
        Args:
            text: 用户消息
            chat_id: 会话 ID
            owner_id: 所有者 ID (S035)
            
        Returns:
            Agent 回复
        """
        logger.info(f"🤖 正在调用 Agent 处理...")
        
        try:
            # 调用 Agent
            response = await self.agent.send_message(text)
            
            # 记录回复
            logger.info(f"🤖 Agent 回复: {response[:100]}{'...' if len(response) > 100 else ''}")
            return response
            
        except asyncio.TimeoutError:
            logger.error("⏱️ Agent 处理超时")
            return "抱歉，处理超时了，请稍后重试。"
            
        except ConnectionError as e:
            logger.error(f"🌐 网络连接错误: {e}")
            return "抱歉，网络连接有问题，请检查网络后重试。"
            
        except Exception as e:
            logger.exception(f"❌ Agent 处理异常: {e}")
            return "抱歉，处理你的请求时出现了错误，请稍后重试。"
    
    async def start(self):
        """启动 Bot"""
        await self.initialize()
        
        # 使用装饰器注册消息处理
        @self.client.on_message
        async def handle(update: TelegramUpdate):
            await self.handle_message(update)
        
        # 启动 Long Polling
        await self.client.start_polling()
        
        logger.info("Telegram Bot 服务已启动，等待消息...")
        
        self.running = True
        
        # 保持运行
        while self.running:
            await asyncio.sleep(3600)
    
    async def stop(self):
        """停止 Bot"""
        logger.info("正在停止 Bot...")
        self.running = False
        
        if self.agent:
            await self.agent.stop()
        
        if self.client:
            await self.client.close()
        
        logger.info("Bot 已停止")


async def main():
    """主函数"""
    bot = WukongBot()
    
    # 设置信号处理
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("收到退出信号")
        asyncio.create_task(bot.stop())
    
    # 注册信号处理器
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            pass
    
    # 启动 Bot
    try:
        await bot.start()
    except asyncio.CancelledError:
        logger.info("任务被取消")
    except Exception as e:
        logger.exception("Bot 运行异常: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
