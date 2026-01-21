import os
import logging

logger = logging.getLogger(__name__)

# 环境配置
env = os.getenv('ENV', 'local')

# 飞书配置
lark_bot_id = os.getenv('LARKBOT_ID')
lark_webhook_url = os.getenv('LARK_WEBHOOK_URL', '')
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')

# 如果没有配置完整的webhook URL，使用lark_bot_id构建
if not lark_webhook_url and lark_bot_id:
    lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}'
    logger.info(f"使用LARKBOT_ID构建webhook URL")

# 启动时验证关键配置
if not lark_webhook_url:
    logger.warning("未配置 LARK_WEBHOOK_URL 或 LARKBOT_ID，飞书告警功能将不可用")

if not lark_alert_email:
    logger.warning("未配置 LARK_ALERT_EMAIL，告警消息将无法@指定人员")

# Redis配置
redis_password = os.getenv('REDIS_PASSWORD')
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')