import os
from utils.logging_config import logger

# ============ 环境配置 ============
env = os.getenv('ENV', 'local')

# ============ 飞书配置 ============
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')
lark_bot_id = os.getenv('LARKBOT_ID')
# 启动时验证关键配置
if not lark_bot_id:
    logger.warning("未配置 LARK_WEBHOOK_URL 或 LARKBOT_ID，飞书告警功能将不可用")

if lark_bot_id: 
    lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}'
else:
    lark_webhook_url = None

if not lark_alert_email:
    logger.warning("未配置 LARK_ALERT_EMAIL，告警消息将无法@指定人员")

# ============ Redis配置 ============
redis_password = os.getenv('REDIS_PASSWORD')
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')

# ============ 服务类型配置 ============
SERVICE_TYPE = os.getenv('SERVICE_TYPE', 'general')  # 'general' 或 'hype_purr'

# ============ API 配置 ============
# Hyperliquid API URL (通常不需要修改，除非使用测试网)
HYPERLIQUID_API_URL = os.getenv('HYPERLIQUID_API_URL', 'https://api.hyperliquid.xyz/info')

# ============ 通用服务配置 ============
DEFAULT_BASE_SYMBOL = os.getenv('BASE_SYMBOL', 'BTC/USDC:USDC')
DEFAULT_TIMEFRAMES = ['5m', '1h', '4h']
DEFAULT_BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
DEFAULT_BATCH_TIMEOUT = float(os.getenv('BATCH_TIMEOUT', '5.0'))

# ============ HYPE/PURR 专用配置 ============
HYPE_BASE_SYMBOL = 'HYPE/USDC:USDC'
HYPE_SYMBOLS = ['HYPE/USDC:USDC', 'PURR/USDC:USDC']
# HYPE 版本使用更宽松的相关系数阈值
HYPE_CORR_THRESHOLD = float(os.getenv('HYPE_CORR_THRESHOLD', '0.5'))

# ============ 队列配置 ============
# 通用版本（大规模）
QUEUE_CONFIG_GENERAL = {
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE', '10000')),
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE', '15000')),
    'analysis_result_buffer_size': int(os.getenv('ANALYSIS_RESULT_BUFFER_SIZE', '10000'))
}

# HYPE版本（小规模）
QUEUE_CONFIG_HYPE = {
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE_HYPE', '1000')),
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE_HYPE', '1000')),
    'analysis_result_buffer_size': int(os.getenv('ANALYSIS_RESULT_BUFFER_SIZE_HYPE', '1000'))
}

# ============ 分析参数配置 ============
# 数据充足性阈值
MIN_4H_DATA_POINTS = int(os.getenv('MIN_4H_DATA_POINTS', '358'))
MIN_DATA_POINTS = int(os.getenv('MIN_DATA_POINTS', '100'))

# 数据验证最小点数（用于分析算法）
MIN_POINTS_FOR_CORRELATION = int(os.getenv('MIN_POINTS_FOR_CORRELATION', '20'))
MIN_POINTS_FOR_COINTEGRATION = int(os.getenv('MIN_POINTS_FOR_COINTEGRATION', '30'))
MIN_POINTS_FOR_ZSCORE = int(os.getenv('MIN_POINTS_FOR_ZSCORE', '19'))

# 相关系数过滤阈值（关键参数）
TARGET_CORR_THRESHOLD = float(os.getenv('TARGET_CORR_THRESHOLD', '0.6'))
# 注意：HYPE 版本会使用 HYPE_CORR_THRESHOLD (0.5) 而非此默认值

# 协整检验参数
COINTEGRATION_SIGNIFICANCE_LEVEL = float(os.getenv('COINTEGRATION_SIGNIFICANCE_LEVEL', '0.05'))

# 数据窗口配置（天数）
DATA_WINDOW_CONFIG = {
    '5m': int(os.getenv('DATA_WINDOW_5M', '7')),
    '1h': int(os.getenv('DATA_WINDOW_1H', '30')),
    '4h': int(os.getenv('DATA_WINDOW_4H', '60'))
}

# 分析算法参数
BETA_WINDOW = int(os.getenv('BETA_WINDOW', '100'))
ZSCORE_WINDOW = int(os.getenv('ZSCORE_WINDOW', '30'))
COINTEGRATION_THRESHOLD = int(os.getenv('COINTEGRATION_THRESHOLD', '2'))

# Z-score 阈值
ZSCORE_THRESHOLDS = {
    'long': float(os.getenv('ZSCORE_THRESHOLD_LONG', '0.2')),
    'middle': float(os.getenv('ZSCORE_THRESHOLD_MIDDLE', '1.5')),
    'short': float(os.getenv('ZSCORE_THRESHOLD_SHORT', '1.8'))
}

# ============ 去重配置 ============
# 入队去重窗口（秒）
ENQUEUE_DEDUP_WINDOWS = {
    '5m': int(os.getenv('ENQUEUE_DEDUP_5M', '30')),
    '1h': int(os.getenv('ENQUEUE_DEDUP_1H', '180')),
    '4h': int(os.getenv('ENQUEUE_DEDUP_4H', '600'))
}

# 分析去重窗口（秒）
DEDUP_WINDOWS = {
    '5m': int(os.getenv('DEDUP_5M', '60')),
    '1h': int(os.getenv('DEDUP_1H', '300')),
    '4h': int(os.getenv('DEDUP_4H', '900'))
}

CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '300'))
MAX_RECENT_TASKS = int(os.getenv('MAX_RECENT_TASKS', '5000'))

# ============ WebSocket 配置 ============
WS_TIMEOUT = int(os.getenv('WS_TIMEOUT', '30'))
WS_MAX_RETRIES = int(os.getenv('WS_MAX_RETRIES', '30'))
WS_ALERT_THRESHOLD = int(os.getenv('WS_ALERT_THRESHOLD', '5'))

# ============ 工作线程配置 ============
ANALYSIS_WORKERS_GENERAL = int(os.getenv('ANALYSIS_WORKERS', '15'))
ANALYSIS_WORKERS_HYPE = int(os.getenv('ANALYSIS_WORKERS_HYPE', '2'))

# ============ 批量写入配置 ============
ANALYSIS_RESULT_BATCH_SIZE = int(os.getenv('ANALYSIS_RESULT_BATCH_SIZE', '100'))
ANALYSIS_RESULT_BATCH_TIMEOUT = float(os.getenv('ANALYSIS_RESULT_BATCH_TIMEOUT', '2.0'))
ANALYSIS_USE_COPY_METHOD = os.getenv('ANALYSIS_USE_COPY_METHOD', 'false').lower() in ('true', '1', 'yes')

# ============ 监控配置 ============
QUEUE_MONITOR_INTERVAL = int(os.getenv('QUEUE_MONITOR_INTERVAL', '60'))
QUEUE_WARNING_THRESHOLD = float(os.getenv('QUEUE_WARNING_THRESHOLD', '0.8'))

# ============ 日志配置 ============
# 注意：这些配置在 utils/logging_config.py 中使用
# 如果需要统一管理，可以从 config.py 导入
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(100 * 1024 * 1024)))  # 100MB
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))