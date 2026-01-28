import os
from utils.logging_config import logger

# ============ 环境配置 ============
env = os.getenv('ENV', 'local')

# ============ 飞书配置 ============
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')
lark_bot_id = os.getenv('LARKBOT_ID')
# 启动时验证关键配置
if not lark_bot_id:
    logger.warning("未配置 LARKBOT_ID，飞书告警功能将不可用")

if lark_bot_id: 
    lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}'
else:
    lark_webhook_url = None

if not lark_alert_email:
    logger.warning("未配置 LARK_ALERT_EMAIL，告警消息将无法@指定人员")

# ============ Redis配置 ============
redis_password = os.getenv('REDIS_PASSWORD')
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')

# ============ TimescaleDB 配置 ============
# 数据库连接配置
TIMESCALEDB_HOST = os.getenv('TIMESCALEDB_HOST', '127.0.0.1')
TIMESCALEDB_PORT = int(os.getenv('TIMESCALEDB_PORT', '5432'))
TIMESCALEDB_NAME = os.getenv('TIMESCALEDB_NAME', 'crypto_data')
TIMESCALEDB_USER = os.getenv('TIMESCALEDB_USER', 'postgres')
TIMESCALEDB_PASSWORD = os.getenv('TIMESCALEDB_PASSWORD', 'postgres')

# 连接池配置
TIMESCALEDB_POOL_MIN_SIZE = int(os.getenv('TIMESCALEDB_POOL_MIN_SIZE', '2'))
TIMESCALEDB_POOL_MAX_SIZE = int(os.getenv('TIMESCALEDB_POOL_MAX_SIZE', '10'))
TIMESCALEDB_POOL_TIMEOUT = float(os.getenv('TIMESCALEDB_POOL_TIMEOUT', '30.0'))
TIMESCALEDB_POOL_MAX_LIFETIME = int(os.getenv('TIMESCALEDB_POOL_MAX_LIFETIME', '3600'))
TIMESCALEDB_POOL_MAX_IDLE = int(os.getenv('TIMESCALEDB_POOL_MAX_IDLE', '600'))

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

# ============ OLS 协整分析参数 ============
MIN_POINTS_FOR_OLS = int(os.getenv('MIN_POINTS_FOR_OLS', '10'))
MIN_POINTS_FOR_HEALTH_MONITOR = int(os.getenv('MIN_POINTS_FOR_HEALTH_MONITOR', '200'))

# 协整模型选择阈值
ALPHA_SIGNIFICANCE_LEVEL = float(os.getenv('ALPHA_SIGNIFICANCE_LEVEL', '0.05'))
ALPHA_CROSS_ASSET_THRESHOLD = float(os.getenv('ALPHA_CROSS_ASSET_THRESHOLD', '5'))
ALPHA_SAME_ASSET_THRESHOLD = float(os.getenv('ALPHA_SAME_ASSET_THRESHOLD', '2'))

# ============ 信号强度阈值 ============
ZSCORE_STRONG_THRESHOLD = float(os.getenv('ZSCORE_STRONG_THRESHOLD', '2.5'))
ZSCORE_MEDIUM_THRESHOLD = float(os.getenv('ZSCORE_MEDIUM_THRESHOLD', '2.0'))

# ============ 健康监控参数 ============
HEALTH_MONITOR_LONG_WINDOW = int(os.getenv('HEALTH_MONITOR_LONG_WINDOW', '200'))
HEALTH_MONITOR_SHORT_WINDOW = int(os.getenv('HEALTH_MONITOR_SHORT_WINDOW', '100'))
HEALTH_MONITOR_STATE_THRESHOLDS = tuple(map(int, os.getenv('HEALTH_MONITOR_STATE_THRESHOLDS', '18,14,10').split(',')))
HEALTH_MONITOR_PERIOD = tuple(os.getenv('HEALTH_MONITOR_PERIOD', '4h,60d').split(','))

# ============ 多周期分析配置 ============
REQUIRED_PERIODS = [
    tuple(p.split(',')) for p in os.getenv('REQUIRED_PERIODS', '5m,7d;1h,30d;4h,60d').split(';')
]

# ============ 告警格式化配置 ============
# 信号强度判断阈值
ALERT_SIGNAL_STRENGTH_EXTREME = float(os.getenv('ALERT_SIGNAL_STRENGTH_EXTREME', '1.5'))  # 极强信号阈值
ALERT_SIGNAL_STRENGTH_STRONG = float(os.getenv('ALERT_SIGNAL_STRENGTH_STRONG', '1.0'))    # 强信号阈值
ALERT_SIGNAL_STRENGTH_MEDIUM = float(os.getenv('ALERT_SIGNAL_STRENGTH_MEDIUM', '0.5'))    # 中等信号阈值

# 信号质量评估阈值（基于协整通过数量）
ALERT_QUALITY_EXCELLENT = int(os.getenv('ALERT_QUALITY_EXCELLENT', '5'))  # 优秀质量阈值
ALERT_QUALITY_GOOD = int(os.getenv('ALERT_QUALITY_GOOD', '4'))            # 良好质量阈值
ALERT_QUALITY_FAIR = int(os.getenv('ALERT_QUALITY_FAIR', '3'))            # 一般质量阈值

# 相关系数评级阈值
ALERT_CORR_EXCELLENT = float(os.getenv('ALERT_CORR_EXCELLENT', '0.8'))  # 相关系数优秀阈值（绿色）
ALERT_CORR_GOOD = float(os.getenv('ALERT_CORR_GOOD', '0.6'))            # 相关系数良好阈值（黄色）

# Hurst指数判断阈值
ALERT_HURST_TREND = float(os.getenv('ALERT_HURST_TREND', '0.6'))                    # Hurst趋势阈值（>此值为趋势性）
ALERT_HURST_MEAN_REVERSION = float(os.getenv('ALERT_HURST_MEAN_REVERSION', '0.4'))  # Hurst均值回复阈值（<此值为均值回复）

# 健康监控窗口对比阈值
ALERT_SCORE_DIFF_HIGH = int(os.getenv('ALERT_SCORE_DIFF_HIGH', '15'))      # 得分差异过大阈值
ALERT_SCORE_DIFF_MEDIUM = int(os.getenv('ALERT_SCORE_DIFF_MEDIUM', '10'))  # 得分差异需关注阈值
ALERT_SCORE_DETERIORATE = int(os.getenv('ALERT_SCORE_DETERIORATE', '5'))   # 短期恶化判断阈值

# 风险评估 - 高风险因素阈值
ALERT_RISK_HIGH_SCORE_MIN = int(os.getenv('ALERT_RISK_HIGH_SCORE_MIN', '10'))        # 高风险：最低得分阈值
ALERT_RISK_HIGH_SCORE_DIFF = int(os.getenv('ALERT_RISK_HIGH_SCORE_DIFF', '15'))      # 高风险：得分差异阈值
ALERT_RISK_HIGH_HURST = float(os.getenv('ALERT_RISK_HIGH_HURST', '0.7'))             # 高风险：Hurst阈值

# 风险评估 - 中等风险因素阈值
ALERT_RISK_MID_COINT_MIN = int(os.getenv('ALERT_RISK_MID_COINT_MIN', '3'))           # 中风险：协整最低通过数
ALERT_RISK_MID_ZSCORE_RATIO = int(os.getenv('ALERT_RISK_MID_ZSCORE_RATIO', '3'))     # 中风险：Z-score倍数（短周期/长周期）
ALERT_RISK_MID_SCORE_MIN = int(os.getenv('ALERT_RISK_MID_SCORE_MIN', '18'))          # 中风险：得分阈值（WARNING/DANGER状态）
ALERT_RISK_MID_BETA_CV = float(os.getenv('ALERT_RISK_MID_BETA_CV', '0.2'))           # 中风险：β变异系数阈值

# 风险评估 - 有利因素阈值
ALERT_RISK_GREEN_SCORE_MIN = int(os.getenv('ALERT_RISK_GREEN_SCORE_MIN', '18'))      # 有利因素：健康得分阈值
ALERT_RISK_GREEN_CORR_MIN = float(os.getenv('ALERT_RISK_GREEN_CORR_MIN', '0.6'))     # 有利因素：相关系数阈值
ALERT_RISK_GREEN_COINT_MIN = int(os.getenv('ALERT_RISK_GREEN_COINT_MIN', '4'))       # 有利因素：协整通过数阈值

# 综合评级判断阈值
ALERT_RATING_HIGH_COUNT = int(os.getenv('ALERT_RATING_HIGH_COUNT', '2'))    # 评级：高风险数量阈值
ALERT_RATING_MID_COUNT = int(os.getenv('ALERT_RATING_MID_COUNT', '2'))      # 评级：中风险数量阈值
ALERT_RATING_GREEN_COUNT = int(os.getenv('ALERT_RATING_GREEN_COUNT', '2'))  # 评级：有利因素数量阈值