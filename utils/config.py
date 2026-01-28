import os
from utils.logging_config import logger

# ============ 敏感信息（保留环境变量） ============
lark_bot_id = os.getenv('LARKBOT_ID')
lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}' if lark_bot_id else None
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')
redis_password = os.getenv('REDIS_PASSWORD')
TIMESCALEDB_USER = os.getenv('TIMESCALEDB_USER', 'postgres')
TIMESCALEDB_PASSWORD = os.getenv('TIMESCALEDB_PASSWORD', 'postgres')

# ============ 环境配置 ============
env = 'local'

# ============ Redis配置 ============
redis_host = '127.0.0.1'

# ============ TimescaleDB配置 ============
TIMESCALEDB_HOST = '127.0.0.1'
TIMESCALEDB_PORT = 5432
TIMESCALEDB_NAME = 'crypto_data'
TIMESCALEDB_POOL_MIN_SIZE = 2
TIMESCALEDB_POOL_MAX_SIZE = 10
TIMESCALEDB_POOL_TIMEOUT = 30.0
TIMESCALEDB_POOL_MAX_LIFETIME = 3600
TIMESCALEDB_POOL_MAX_IDLE = 600

# ============ 通用服务配置 ============
DEFAULT_BASE_SYMBOL = 'BTC/USDC:USDC'
DEFAULT_TIMEFRAMES = ['5m', '1h', '4h']
DEFAULT_BATCH_SIZE = 1000
DEFAULT_BATCH_TIMEOUT = 5.0

# ============ HYPE/PURR专用配置 ============
HYPE_BASE_SYMBOL = 'HYPE/USDC:USDC'
HYPE_SYMBOLS = ['HYPE/USDC:USDC', 'PURR/USDC:USDC']
HYPE_CORR_THRESHOLD = 0.5

# ============ 队列配置 ============
QUEUE_CONFIG_GENERAL = {'kline_buffer_size': 10000, 'analysis_queue_size': 15000, 'analysis_result_buffer_size': 10000}
QUEUE_CONFIG_HYPE = {'kline_buffer_size': 1000, 'analysis_queue_size': 1000, 'analysis_result_buffer_size': 1000}

# ============ 分析参数配置 ============
MIN_4H_DATA_POINTS = 358
MIN_DATA_POINTS = 100
MIN_POINTS_FOR_CORRELATION = 20
MIN_POINTS_FOR_ZSCORE = 19
TARGET_CORR_THRESHOLD = 0.6
DATA_WINDOW_CONFIG = {'5m': 7, '1h': 30, '4h': 60}
BETA_WINDOW = 100
ZSCORE_WINDOW = 30
COINTEGRATION_THRESHOLD = 2
ZSCORE_THRESHOLDS = {'long': 0.2, 'middle': 1.5, 'short': 1.8, 'strong': 2.5, 'medium': 2.0}

# ============ 去重配置 ============
ENQUEUE_DEDUP_WINDOWS = {'5m': 30, '1h': 180, '4h': 600}
DEDUP_WINDOWS = {'5m': 60, '1h': 300, '4h': 900}
CLEANUP_INTERVAL = 300
MAX_RECENT_TASKS = 5000

# ============ WebSocket配置 ============
WS_TIMEOUT = 30
WS_MAX_RETRIES = 30
WS_ALERT_THRESHOLD = 5

# ============ 工作线程配置 ============
ANALYSIS_WORKERS_GENERAL = 15
ANALYSIS_WORKERS_HYPE = 2

# ============ 批量写入配置 ============
ANALYSIS_RESULT_BATCH_SIZE = 100
ANALYSIS_RESULT_BATCH_TIMEOUT = 2.0
ANALYSIS_USE_COPY_METHOD = False

# ============ 监控配置 ============
QUEUE_MONITOR_INTERVAL = 60
QUEUE_WARNING_THRESHOLD = 0.8

# ============ OLS协整分析参数 ============
MIN_POINTS_FOR_OLS = 10
ALPHA_SIGNIFICANCE_LEVEL = 0.05
ALPHA_CROSS_ASSET_THRESHOLD = 5.0
ALPHA_SAME_ASSET_THRESHOLD = 2.0

# ============ 健康监控参数 ============
HEALTH_MONITOR_LONG_WINDOW = 200
HEALTH_MONITOR_SHORT_WINDOW = 100
HEALTH_MONITOR_STATE_THRESHOLDS = (18, 14, 10)
HEALTH_MONITOR_PERIOD = ('4h', '60d')

# ============ 多周期分析配置 ============
REQUIRED_PERIODS = [('5m', '7d'), ('1h', '30d'), ('4h', '60d')]

# ============ 告警格式化配置 ============
ALERT_SIGNAL_STRENGTH = {'extreme': 1.5, 'strong': 1.0, 'medium': 0.5}
ALERT_QUALITY = {'excellent': 5, 'good': 4, 'fair': 3}
ALERT_CORR = {'excellent': 0.8, 'good': 0.6}
ALERT_HURST = {'trend': 0.6, 'mean_reversion': 0.4}
ALERT_SCORE_DIFF = {'high': 15, 'medium': 10, 'deteriorate': 5}
ALERT_RISK_HIGH_SCORE_MIN = HEALTH_MONITOR_STATE_THRESHOLDS[2]
ALERT_RISK_HIGH_HURST = 0.7
ALERT_RISK_MID = {'coint_min': 3, 'zscore_ratio': 3, 'beta_cv': 0.2}
ALERT_RISK_GREEN_SCORE_MIN = HEALTH_MONITOR_STATE_THRESHOLDS[0]
ALERT_RATING_COUNT_THRESHOLD = 2

# ============ WebSocket 高级配置 ============
WS_PING_INTERVAL_MS = int(os.getenv('WS_PING_INTERVAL_MS', '50'))  # Ping间隔(毫秒)
WS_PING_THREAD_SHUTDOWN_TIMEOUT = float(os.getenv('WS_PING_THREAD_SHUTDOWN_TIMEOUT', '2.0'))  # Ping线程关闭超时(秒)
WS_STATE_VALIDATION_DELAY = float(os.getenv('WS_STATE_VALIDATION_DELAY', '1.0'))  # 状态验证延迟(秒)
WS_READY_TIMEOUT = float(os.getenv('WS_READY_TIMEOUT', '5.0'))  # WebSocket就绪超时(秒)
WS_RECONNECT_MIN_DELAY = float(os.getenv('WS_RECONNECT_MIN_DELAY', '0.1'))  # 重连最小延迟(秒)
WS_RECONNECT_INITIAL_DELAY = float(os.getenv('WS_RECONNECT_INITIAL_DELAY', '1.0'))  # 重连初始延迟(秒)
WS_RECONNECT_MAX_DELAY = float(os.getenv('WS_RECONNECT_MAX_DELAY', '60.0'))  # 重连最大延迟(秒)
WS_RECONNECT_MULTIPLIER = float(os.getenv('WS_RECONNECT_MULTIPLIER', '2.0'))  # 重连延迟倍数
WS_RECONNECT_JITTER = float(os.getenv('WS_RECONNECT_JITTER', '0.25'))  # 重连抖动系数

# ============ 分析算法高级配置 ============
CORRELATION_METHOD = os.getenv('CORRELATION_METHOD', 'pearson')  # 相关系数计算方法: pearson/kendall/spearman
ADF_LAG_SELECTION_METHOD = os.getenv('ADF_LAG_SELECTION_METHOD', 'AIC')  # ADF检验滞后选择: AIC/BIC/t-stat
DEFAULT_ZSCORE_THRESHOLD = float(os.getenv('DEFAULT_ZSCORE_THRESHOLD', '2.0'))  # 默认Z-score阈值

# ============ K线数据补充器配置 ============
KLINE_FILLER_COOLDOWN_SECONDS = int(os.getenv('KLINE_FILLER_COOLDOWN_SECONDS', '600'))  # 补充冷却时间(秒)
KLINE_FILLER_API_INTERVAL = float(os.getenv('KLINE_FILLER_API_INTERVAL', '1.5'))  # API请求间隔(秒)
KLINE_FILLER_MAX_RETRIES = int(os.getenv('KLINE_FILLER_MAX_RETRIES', '3'))  # 最大重试次数
KLINE_FILLER_API_LIMIT = int(os.getenv('KLINE_FILLER_API_LIMIT', '1500'))  # API单次查询限制
KLINE_FILLER_CLEANUP_INTERVAL = int(os.getenv('KLINE_FILLER_CLEANUP_INTERVAL', '100'))  # 清理间隔(次)
KLINE_FILLER_LAZY_RATE_LIMIT = int(os.getenv('KLINE_FILLER_LAZY_RATE_LIMIT', '1500'))  # Lazy模式速率限制(ms)
KLINE_FILLER_LAZY_TIMEOUT_MS = int(os.getenv('KLINE_FILLER_LAZY_TIMEOUT_MS', '30000'))  # Lazy模式超时(ms)

# ============ 飞书告警高级配置 ============
LARK_MAX_RETRIES = int(os.getenv('LARK_MAX_RETRIES', '3'))  # 最大重试次数
LARK_REQUEST_TIMEOUT = float(os.getenv('LARK_REQUEST_TIMEOUT', '10.0'))  # 请求超时(秒)
LARK_BACKOFF_BASE = int(os.getenv('LARK_BACKOFF_BASE', '2'))  # 指数退避基数

# ============ 调度器配置 ============
SCHEDULER_WEEKDAY_CHECK_INTERVAL = int(os.getenv('SCHEDULER_WEEKDAY_CHECK_INTERVAL', '60'))  # 工作日检查间隔(秒)
SCHEDULER_TIME_CHECK_INTERVAL = int(os.getenv('SCHEDULER_TIME_CHECK_INTERVAL', '10'))  # 时间检查间隔(秒)
SCHEDULER_EXECUTION_WINDOW_MINUTES = int(os.getenv('SCHEDULER_EXECUTION_WINDOW_MINUTES', '10'))  # 执行窗口(分钟)
SCHEDULER_POST_EXECUTION_WAIT_SECONDS = int(os.getenv('SCHEDULER_POST_EXECUTION_WAIT_SECONDS', '3600'))  # 执行后等待(秒)

# ============ 服务线程超时配置 ============
QUEUE_GET_TIMEOUT = float(os.getenv('QUEUE_GET_TIMEOUT', '1.0'))  # 队列读取超时(秒)
WORKER_THREAD_SHUTDOWN_TIMEOUT = float(os.getenv('WORKER_THREAD_SHUTDOWN_TIMEOUT', '5.0'))  # 工作线程关闭超时(秒)
MAIN_THREAD_SHUTDOWN_TIMEOUT = float(os.getenv('MAIN_THREAD_SHUTDOWN_TIMEOUT', '10.0'))  # 主线程关闭超时(秒)
CPU_CHECK_INTERVAL = float(os.getenv('CPU_CHECK_INTERVAL', '0.1'))  # CPU检查间隔(秒)
DB_QUERY_LIMIT = int(os.getenv('DB_QUERY_LIMIT', '10000'))  # 数据库查询限制

# ============ 协整健康监控参数扩展 ============
# 注: HEALTH_MONITOR_LONG_WINDOW/SHORT_WINDOW等已在上方定义
HEALTH_MONITOR_MAX_HALFLIFE = int(os.getenv('HEALTH_MONITOR_MAX_HALFLIFE', '30'))  # 半衰期上限(用于协整检查)
HEALTH_MONITOR_MIN_HALFLIFE = int(os.getenv('HEALTH_MONITOR_MIN_HALFLIFE', '5'))  # 半衰期下限
HEALTH_MONITOR_SCORE_WEIGHTS = tuple(map(float, os.getenv('HEALTH_MONITOR_SCORE_WEIGHTS', '0.4,0.3,0.3').split(',')))  # 得分权重(ADF,半衰期,稳定性)

# ============ 告警格式化配置扩展 ============
ALERT_PROGRESS_BAR_WIDTH = int(os.getenv('ALERT_PROGRESS_BAR_WIDTH', '10'))  # 进度条宽度
ALERT_ZSCORE_MAX_VALUE = float(os.getenv('ALERT_ZSCORE_MAX_VALUE', '3.0'))  # Z-score最大显示值
