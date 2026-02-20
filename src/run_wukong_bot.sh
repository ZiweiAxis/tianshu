#!/bin/bash
# 启动悟空 Bot
# 使用: ./run_wukong_bot.sh

# 设置环境变量
export TELEGRAM_WUKONG_BOT_TOKEN="8009312914:AAHNJlIvSvmITzuawlRxRLer06Z5klPgnvc"
export HTTP_PROXY="http://192.168.3.16:7890"
export HTTPS_PROXY="http://192.168.3.16:7890"

# 可选: Claude API
# export ANTHROPIC_API_KEY="your_api_key"

cd /home/dministrator/workspace/ziwei/tianshu/src
python3 wukong_handler.py
