import os
from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载

# ---------- 飞书 ----------
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")

# ---------- Matrix ----------
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER")
MATRIX_GATEWAY_USER = os.getenv("MATRIX_GATEWAY_USER")
MATRIX_GATEWAY_TOKEN = os.getenv("MATRIX_GATEWAY_TOKEN")
# 谛听 Matrix 账号
DITING_MATRIX_TOKEN = os.getenv("DITING_MATRIX_TOKEN")
# 审批用户 ID（发送审批请求的目标）
APPROVAL_USER_ID = os.getenv("APPROVAL_USER_ID")
# DM 映射文件路径
DM_MAPPING_FILE = os.getenv("DM_MAPPING_FILE", "/data/dm_mapping.json")

USE_PRIVATE_ROOM = os.getenv("USE_PRIVATE_ROOM", "false").lower() == "true"
SHARED_ROOM_ID = os.getenv("SHARED_ROOM_ID")
# E2-S3：业务层发投递事件时使用的 Room（Bridge 需已加入）；不设则由调用方指定 room_id
DELIVERY_ROOM_ID = os.getenv("DELIVERY_ROOM_ID")

# ---------- 谛听 ----------
DITING_AUDIT_URL = os.getenv("DITING_AUDIT_URL")
DITING_APPROVE_CALLBACK_URL = os.getenv("DITING_APPROVE_CALLBACK_URL")
# E4-S4：Agent 注册完成后通知谛听初始化权限（POST 含 agent_id、owner_id）
DITING_INIT_PERMISSION_URL = os.getenv("DITING_INIT_PERMISSION_URL")
# E9-S1：主 Agent 登记 Sub-agent 后可选通知谛听（POST 含 main_agent_id, sub_agent_id）
DITING_SUB_AGENT_REGISTER_URL = os.getenv("DITING_SUB_AGENT_REGISTER_URL")
# I-018：谛听链上 DID 接口基址（如 http://diting:8080/chain），用于注册/心跳调用 DID 注册与查询
DITING_CHAIN_URL = os.getenv("DITING_CHAIN_URL")
# E1-S3：无回复时推送给用户的反馈文案（可配置）
FEEDBACK_NO_REPLY = os.getenv("FEEDBACK_NO_REPLY", "已触达，等待处理。若长时间无回复请重试或联系管理员。")

# E11-S3：健康与就绪探针 HTTP 端口
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL")
