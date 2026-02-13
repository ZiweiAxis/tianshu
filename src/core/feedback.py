# E1-S3：无回复时的明确反馈
from src.config import FEEDBACK_NO_REPLY

def get_no_reply_feedback_message(custom_message=None):
    return (custom_message or "").strip() or (FEEDBACK_NO_REPLY or "已触达，等待处理。")
