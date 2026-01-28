import os
from utils.logging_config import logger

# ============ 环境配置 ============
env = os.getenv('ENV', 'local')  # 运行环境: local/dev/staging/production

# ============ 飞书配置 ============
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')  # 告警@人员邮箱
lark_bot_id = os.getenv('LARKBOT_ID')  # 飞书机器人ID，用于构建webhook URL

if not lark_bot_id:
    logger.warning("未配置 LARKBOT_ID，飞书告警功能将不可用")

if lark_bot_id:
    lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}'
else:
    lark_webhook_url = None

if not lark_alert_email:
    logger.warning("未配置 LARK_ALERT_EMAIL，告警消息将无法@指定人员")

# ============ Redis配置 ============
redis_password = os.getenv('REDIS_PASSWORD')  # Redis认证密码
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')  # Redis服务器地址

# ============ TimescaleDB 配置 ============
TIMESCALEDB_HOST = os.getenv('TIMESCALEDB_HOST', '127.0.0.1')  # 数据库服务器地址
TIMESCALEDB_PORT = int(os.getenv('TIMESCALEDB_PORT', '5432'))  # 数据库端口
TIMESCALEDB_NAME = os.getenv('TIMESCALEDB_NAME', 'crypto_data')  # 数据库名称
TIMESCALEDB_USER = os.getenv('TIMESCALEDB_USER', 'postgres')  # 数据库用户名
TIMESCALEDB_PASSWORD = os.getenv('TIMESCALEDB_PASSWORD', 'postgres')  # 数据库密码（生产环境务必修改）

# 连接池配置
TIMESCALEDB_POOL_MIN_SIZE = int(os.getenv('TIMESCALEDB_POOL_MIN_SIZE', '2'))  # 最小连接数
TIMESCALEDB_POOL_MAX_SIZE = int(os.getenv('TIMESCALEDB_POOL_MAX_SIZE', '10'))  # 最大连接数
TIMESCALEDB_POOL_TIMEOUT = float(os.getenv('TIMESCALEDB_POOL_TIMEOUT', '30.0'))  # 连接获取超时（秒）
TIMESCALEDB_POOL_MAX_LIFETIME = int(os.getenv('TIMESCALEDB_POOL_MAX_LIFETIME', '3600'))  # 连接最大生命周期（秒）
TIMESCALEDB_POOL_MAX_IDLE = int(os.getenv('TIMESCALEDB_POOL_MAX_IDLE', '600'))  # 连接最大空闲时间（秒）

# ============ 通用服务配置 ============
DEFAULT_BASE_SYMBOL = os.getenv('BASE_SYMBOL', 'BTC/USDC:USDC')  # 配对交易基准资产
DEFAULT_TIMEFRAMES = ['5m', '1h', '4h']  # 分析时间周期列表
DEFAULT_BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))  # K线批量获取大小
DEFAULT_BATCH_TIMEOUT = float(os.getenv('BATCH_TIMEOUT', '5.0'))  # 批量操作超时（秒）

# ============ HYPE/PURR 专用配置 ============
HYPE_BASE_SYMBOL = 'HYPE/USDC:USDC'  # HYPE专用版基准交易对
HYPE_SYMBOLS = ['HYPE/USDC:USDC', 'PURR/USDC:USDC']  # HYPE专用版监控交易对
HYPE_CORR_THRESHOLD = float(os.getenv('HYPE_CORR_THRESHOLD', '0.5'))  # HYPE版相关系数阈值（比通用版0.6更宽松）

# ============ 队列配置 ============
# 通用版本队列配置（大规模多交易对监控，内存约35MB）
QUEUE_CONFIG_GENERAL = {
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE', '10000')),  # K线数据接收缓冲区
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE', '15000')),  # 分析任务队列
    'analysis_result_buffer_size': int(os.getenv('ANALYSIS_RESULT_BUFFER_SIZE', '10000'))  # 分析结果缓冲区
}

# HYPE专用版队列配置（仅2个交易对，内存约3MB）
QUEUE_CONFIG_HYPE = {
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE_HYPE', '1000')),
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE_HYPE', '1000')),
    'analysis_result_buffer_size': int(os.getenv('ANALYSIS_RESULT_BUFFER_SIZE_HYPE', '1000'))
}

# ============ 分析参数配置 ============
# 数据充足性阈值
MIN_4H_DATA_POINTS = int(os.getenv('MIN_4H_DATA_POINTS', '358'))  # 4h周期最小数据点（≈60天）
MIN_DATA_POINTS = int(os.getenv('MIN_DATA_POINTS', '100'))  # 通用最小数据点数

# 各分析算法最小数据点数
MIN_POINTS_FOR_CORRELATION = int(os.getenv('MIN_POINTS_FOR_CORRELATION', '20'))  # 相关系数计算
MIN_POINTS_FOR_COINTEGRATION = int(os.getenv('MIN_POINTS_FOR_COINTEGRATION', '30'))  # 协整检验（ADF）
MIN_POINTS_FOR_ZSCORE = int(os.getenv('MIN_POINTS_FOR_ZSCORE', '19'))  # Z-score计算

# 相关系数过滤阈值（>=0.6才进入协整分析，HYPE版使用HYPE_CORR_THRESHOLD=0.5）
TARGET_CORR_THRESHOLD = float(os.getenv('TARGET_CORR_THRESHOLD', '0.6'))
# 协整检验显著性水平（p-value < 0.05 → 95%置信度认为存在协整关系）
COINTEGRATION_SIGNIFICANCE_LEVEL = float(os.getenv('COINTEGRATION_SIGNIFICANCE_LEVEL', '0.05'))

# 数据窗口配置（天数）：各周期回溯的历史数据长度
DATA_WINDOW_CONFIG = {
    '5m': int(os.getenv('DATA_WINDOW_5M', '7')),  # 5分钟周期，7天≈2016点
    '1h': int(os.getenv('DATA_WINDOW_1H', '30')),  # 1小时周期，30天≈720点
    '4h': int(os.getenv('DATA_WINDOW_4H', '60'))  # 4小时周期，60天≈360点
}

# 分析算法参数
BETA_WINDOW = int(os.getenv('BETA_WINDOW', '100'))  # Beta系数计算窗口（OLS回归对冲比率）
ZSCORE_WINDOW = int(os.getenv('ZSCORE_WINDOW', '30'))  # Z-score计算窗口
COINTEGRATION_THRESHOLD = int(os.getenv('COINTEGRATION_THRESHOLD', '2'))  # 协整通过门槛数

# Z-score交易信号阈值
ZSCORE_THRESHOLDS = {
    'long': float(os.getenv('ZSCORE_THRESHOLD_LONG', '0.2')),  # 做多信号（4h长周期）
    'middle': float(os.getenv('ZSCORE_THRESHOLD_MIDDLE', '1.5')),  # 中性信号（1h中周期）
    'short': float(os.getenv('ZSCORE_THRESHOLD_SHORT', '1.8')),  # 做空信号（5m短周期）
    'strong': float(os.getenv('ZSCORE_STRONG_THRESHOLD', '2.5')),  # 强信号阈值
    'medium': float(os.getenv('ZSCORE_MEDIUM_THRESHOLD', '2.0')),  # 中等信号阈值
}

# ============ 去重配置 ============
# 入队去重窗口（秒）：同一(交易对, 周期)组合在窗口内只能入队一次
ENQUEUE_DEDUP_WINDOWS = {
    '5m': int(os.getenv('ENQUEUE_DEDUP_5M', '30')),  # 30秒
    '1h': int(os.getenv('ENQUEUE_DEDUP_1H', '180')),  # 3分钟
    '4h': int(os.getenv('ENQUEUE_DEDUP_4H', '600'))  # 10分钟
}

# 分析去重窗口（秒）：执行层面去重，比入队去重更严格
DEDUP_WINDOWS = {
    '5m': int(os.getenv('DEDUP_5M', '60')),  # 1分钟
    '1h': int(os.getenv('DEDUP_1H', '300')),  # 5分钟
    '4h': int(os.getenv('DEDUP_4H', '900'))  # 15分钟
}

CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '300'))  # 去重记录清理间隔（秒）
MAX_RECENT_TASKS = int(os.getenv('MAX_RECENT_TASKS', '5000'))  # 最近任务记录数上限

# ============ WebSocket 配置 ============
WS_TIMEOUT = int(os.getenv('WS_TIMEOUT', '30'))  # 连接超时（秒）
WS_MAX_RETRIES = int(os.getenv('WS_MAX_RETRIES', '30'))  # 最大重连次数
WS_ALERT_THRESHOLD = int(os.getenv('WS_ALERT_THRESHOLD', '5'))  # 连续失败多少次触发告警

# ============ 工作线程配置 ============
ANALYSIS_WORKERS_GENERAL = int(os.getenv('ANALYSIS_WORKERS', '15'))  # 通用版工作线程数（推荐=CPU核心数*1.5-2）
ANALYSIS_WORKERS_HYPE = int(os.getenv('ANALYSIS_WORKERS_HYPE', '2'))  # HYPE专用版工作线程数

# ============ 批量写入配置 ============
ANALYSIS_RESULT_BATCH_SIZE = int(os.getenv('ANALYSIS_RESULT_BATCH_SIZE', '100'))  # 批量写入大小
ANALYSIS_RESULT_BATCH_TIMEOUT = float(os.getenv('ANALYSIS_RESULT_BATCH_TIMEOUT', '2.0'))  # 强制写入超时（秒）
ANALYSIS_USE_COPY_METHOD = os.getenv('ANALYSIS_USE_COPY_METHOD', 'false').lower() in ('true', '1', 'yes')  # 使用COPY方法（大批量时性能更好）

# ============ 监控配置 ============
QUEUE_MONITOR_INTERVAL = int(os.getenv('QUEUE_MONITOR_INTERVAL', '60'))  # 队列监控检查间隔（秒）
QUEUE_WARNING_THRESHOLD = float(os.getenv('QUEUE_WARNING_THRESHOLD', '0.8'))  # 队列使用率告警阈值（80%）

# ============ OLS 协整分析参数 ============
MIN_POINTS_FOR_OLS = int(os.getenv('MIN_POINTS_FOR_OLS', '10'))  # OLS回归最小数据点数

# 协整模型选择阈值（判断使用带截距或不带截距模型）
ALPHA_SIGNIFICANCE_LEVEL = float(os.getenv('ALPHA_SIGNIFICANCE_LEVEL', '0.05'))  # α显著性水平
ALPHA_CROSS_ASSET_THRESHOLD = float(os.getenv('ALPHA_CROSS_ASSET_THRESHOLD', '5'))  # 跨资产Alpha阈值（|α|>5→无截距模型）
ALPHA_SAME_ASSET_THRESHOLD = float(os.getenv('ALPHA_SAME_ASSET_THRESHOLD', '2'))  # 同资产Alpha阈值（|α|<2→标准EG模型）

# ============ 健康监控参数 ============
# 长窗口（200期）也作为健康监控最小数据点需求
HEALTH_MONITOR_LONG_WINDOW = int(os.getenv('HEALTH_MONITOR_LONG_WINDOW', '200'))  # 长期窗口（4h≈33天）
HEALTH_MONITOR_SHORT_WINDOW = int(os.getenv('HEALTH_MONITOR_SHORT_WINDOW', '100'))  # 短期窗口（4h≈17天）
# 状态分级：>=18 HEALTHY, 14-17 WARNING, 10-13 DANGER, <10 CRITICAL
HEALTH_MONITOR_STATE_THRESHOLDS = tuple(map(int, os.getenv('HEALTH_MONITOR_STATE_THRESHOLDS', '18,14,10').split(',')))
HEALTH_MONITOR_PERIOD = tuple(os.getenv('HEALTH_MONITOR_PERIOD', '4h,60d').split(','))  # 监控周期和数据窗口

# ============ 多周期分析配置 ============
# 必需分析周期列表：所有周期都通过协整检验才认为配对可靠
# 环境变量格式：'5m,7d;1h,30d;4h,60d'
REQUIRED_PERIODS = [
    tuple(p.split(',')) for p in os.getenv('REQUIRED_PERIODS', '5m,7d;1h,30d;4h,60d').split(';')
]

# ============ 告警格式化配置 ============
ALERT_SIGNAL_STRENGTH = {
    'extreme': float(os.getenv('ALERT_SIGNAL_STRENGTH_EXTREME', '1.5')),  # 极强信号
    'strong': float(os.getenv('ALERT_SIGNAL_STRENGTH_STRONG', '1.0')),  # 强信号
    'medium': float(os.getenv('ALERT_SIGNAL_STRENGTH_MEDIUM', '0.5')),  # 中等信号
}
ALERT_QUALITY = {
    'excellent': int(os.getenv('ALERT_QUALITY_EXCELLENT', '5')),  # 优秀：>=5个周期通过
    'good': int(os.getenv('ALERT_QUALITY_GOOD', '4')),  # 良好：>=4个周期通过（也用于有利因素判断）
    'fair': int(os.getenv('ALERT_QUALITY_FAIR', '3')),  # 一般：>=3个周期通过
}
ALERT_CORR = {
    'excellent': float(os.getenv('ALERT_CORR_EXCELLENT', '0.8')),  # 优秀：>=0.8 强正相关
    'good': float(os.getenv('ALERT_CORR_GOOD', '0.6')),  # 良好：>=0.6（也用于有利因素判断）
}
# Hurst < 0.4 均值回复（有利），0.4-0.6 中性，> 0.6 趋势性（不利）
ALERT_HURST = {
    'trend': float(os.getenv('ALERT_HURST_TREND', '0.6')),  # 趋势性阈值
    'mean_reversion': float(os.getenv('ALERT_HURST_MEAN_REVERSION', '0.4')),  # 均值回复阈值
}
ALERT_SCORE_DIFF = {
    'high': int(os.getenv('ALERT_SCORE_DIFF_HIGH', '15')),  # 得分差异过大（也用于高风险因素判断）
    'medium': int(os.getenv('ALERT_SCORE_DIFF_MEDIUM', '10')),  # 得分差异需关注
    'deteriorate': int(os.getenv('ALERT_SCORE_DETERIORATE', '5')),  # 短期恶化早期预警
}
ALERT_RISK_HIGH_SCORE_MIN = HEALTH_MONITOR_STATE_THRESHOLDS[2]  # DANGER分界 (10)
ALERT_RISK_HIGH_HURST = float(os.getenv('ALERT_RISK_HIGH_HURST', '0.7'))  # Hurst>0.7 → 高风险
ALERT_RISK_MID = {
    'coint_min': int(os.getenv('ALERT_RISK_MID_COINT_MIN', '3')),  # 协整通过<3 → 中风险
    'zscore_ratio': int(os.getenv('ALERT_RISK_MID_ZSCORE_RATIO', '3')),  # 短/长Z-score>3倍 → 中风险
    'beta_cv': float(os.getenv('ALERT_RISK_MID_BETA_CV', '0.2')),  # β变异系数>0.2 → 中风险
}
ALERT_RISK_GREEN_SCORE_MIN = HEALTH_MONITOR_STATE_THRESHOLDS[0]  # HEALTHY分界 (18)
# 高风险>=2→不建议交易，中风险>=2→谨慎，有利>=2→推荐
ALERT_RATING_COUNT_THRESHOLD = int(os.getenv('ALERT_RATING_COUNT_THRESHOLD', '2'))  # 因素数量触发阈值（统一）