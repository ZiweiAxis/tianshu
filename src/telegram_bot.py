"""
Telegram 审批 Bot 服务

功能：
- 持续运行处理审批回调
- 用户点击批准/拒绝按钮后调用獬豸 API 完成审批

环境变量：
- TELEGRAM_APPROVAL_BOT_TOKEN: Telegram Bot Token
- XIEZHI_API_URL: 獬豸 API 地址（可选，默认从 DITING_CHAIN_URL 推导）
- HTTP_PROXY / HTTPS_PROXY: 代理配置（可选）

运行方式：
    python telegram_bot.py

Docker 部署：
    docker run -d \
        --name telegram-approval-bot \
        -e TELEGRAM_APPROVAL_BOT_TOKEN=xxx \
        -e XIEZHI_API_URL=http://xiezhi:8080 \
        -e HTTP_PROXY=http://proxy:7890 \
        -e HTTPS_PROXY=http://proxy:7890 \
        telegram-approval-bot:latest
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 导入 Telegram 客户端
from telegram_client import TelegramClient


class ApprovalBot:
    """审批 Bot 主程序"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.running = False
        
    def load_config(self):
        """加载配置"""
        # Telegram Bot Token
        self.token = os.getenv("TELEGRAM_APPROVAL_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            logger.error("请设置 TELEGRAM_APPROVAL_BOT_TOKEN 环境变量")
            sys.exit(1)
        
        # 獬豸 API 地址
        self.xiezhi_api_url = os.getenv("XIEZHI_API_URL")
        
        # 代理配置
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
        
        logger.info("配置加载完成")
        if self.xiezhi_api_url:
            logger.info(f"獬豸 API: {self.xiezhi_api_url}")
        
    async def on_approval(
        self,
        query_id: str,
        request_id: str,
        approved: bool,
    ):
        """
        审批回调处理
        
        Args:
            query_id: Telegram 回调查询 ID
            request_id: 审批请求 ID
            approved: 是否批准
        """
        action = "批准" if approved else "拒绝"
        logger.info(f"审批回调: request_id={request_id}, action={action}")
        
        # 獬豸 API 调用已在 TelegramClient 中自动处理
        # 这里可以添加额外的业务逻辑，如：
        # - 记录审批日志
        # - 发送通知
        # - 更新数据库
        
    async def start(self):
        """启动 Bot"""
        self.load_config()
        
        # 创建 Telegram 客户端
        self.client = TelegramClient(token=self.token)
        
        # 设置审批回调
        self.client.set_approval_callback(self.on_approval)
        
        # 启动 Long Polling
        await self.client.start_polling()
        
        # 获取 Bot 信息
        bot_info = await self.client.get_me()
        if bot_info:
            logger.info(f"Bot 启动成功: @{bot_info.get('username')} ({bot_info.get('first_name')})")
        else:
            logger.error("无法获取 Bot 信息，请检查 Token")
            await self.client.close()
            sys.exit(1)
        
        logger.info("Telegram Bot 服务已启动，等待审批回调...")
        
        self.running = True
        
        # 保持运行
        while self.running:
            await asyncio.sleep(3600)
    
    async def stop(self):
        """停止 Bot"""
        logger.info("正在停止 Bot...")
        self.running = False
        
        if self.client:
            await self.client.close()
        
        logger.info("Bot 已停止")


async def main():
    """主函数"""
    bot = ApprovalBot()
    
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
