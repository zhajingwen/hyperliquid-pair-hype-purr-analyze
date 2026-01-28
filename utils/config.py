import os
from utils.logging_config import logger

# ============ 环境配置 ============
# 运行环境标识
# 用途：区分不同的部署环境，可用于环境特定的配置和行为
# 默认值：'local' - 本地开发环境
# 可选值：'local'（本地）, 'dev'（开发）, 'staging'（预发布）, 'production'（生产）
# 影响范围：可能影响日志级别、数据库连接、告警行为等环境相关功能
env = os.getenv('ENV', 'local')

# ============ 飞书配置 ============
# 飞书告警通知的接收人邮箱
# 用途：在告警消息中@指定人员，确保重要通知能及时到达相关负责人
# 默认值：空字符串（不@任何人）
# 格式：飞书用户的邮箱地址，如 'user@company.com'
# 影响范围：仅影响告警消息的@功能，不影响告警发送本身
lark_alert_email = os.getenv('LARK_ALERT_EMAIL', '')

# 飞书机器人ID
# 用途：构建飞书webhook URL，是发送告警消息的必需配置
# 获取方式：在飞书开放平台创建机器人后获得
# 默认值：None（未配置）
# 影响范围：如果未配置，所有飞书告警功能将不可用
lark_bot_id = os.getenv('LARKBOT_ID')

# 启动时验证关键配置
if not lark_bot_id:
    logger.warning("未配置 LARKBOT_ID，飞书告警功能将不可用")

# 飞书Webhook完整URL
# 用途：发送告警消息的API端点
# 格式：https://open.larksuite.com/open-apis/bot/v2/hook/{bot_id}
# 说明：根据lark_bot_id自动构建，不需要手动配置
if lark_bot_id: 
    lark_webhook_url = f'https://open.larksuite.com/open-apis/bot/v2/hook/{lark_bot_id}'
else:
    lark_webhook_url = None

if not lark_alert_email:
    logger.warning("未配置 LARK_ALERT_EMAIL，告警消息将无法@指定人员")

# ============ Redis配置 ============
# Redis服务器密码
# 用途：连接Redis服务器的认证密码
# 默认值：None（无密码）
# 安全建议：生产环境务必设置强密码
# 影响范围：影响所有Redis连接，包括缓存、去重记录等
redis_password = os.getenv('REDIS_PASSWORD')

# Redis服务器地址
# 用途：指定Redis服务器的IP地址或主机名
# 默认值：'127.0.0.1' - 本地Redis服务
# 影响范围：分布式部署时需要修改为实际Redis服务器地址
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')

# ============ TimescaleDB 配置 ============
# 数据库连接配置
# TimescaleDB是PostgreSQL的时序数据库扩展，用于存储K线数据和分析结果

# 数据库服务器地址
# 用途：TimescaleDB服务器的IP地址或主机名
# 默认值：'127.0.0.1' - 本地数据库
# 影响范围：所有数据库操作
TIMESCALEDB_HOST = os.getenv('TIMESCALEDB_HOST', '127.0.0.1')

# 数据库服务器端口
# 用途：TimescaleDB服务的监听端口
# 默认值：5432 - PostgreSQL标准端口
# 说明：通常无需修改，除非使用非标准端口
TIMESCALEDB_PORT = int(os.getenv('TIMESCALEDB_PORT', '5432'))

# 数据库名称
# 用途：存储加密货币数据的数据库名称
# 默认值：'crypto_data'
# 说明：数据库需要提前创建并安装TimescaleDB扩展
TIMESCALEDB_NAME = os.getenv('TIMESCALEDB_NAME', 'crypto_data')

# 数据库用户名
# 用途：连接数据库使用的用户名
# 默认值：'postgres' - PostgreSQL默认管理员用户
# 权限要求：需要有读写表、创建索引的权限
TIMESCALEDB_USER = os.getenv('TIMESCALEDB_USER', 'postgres')

# 数据库密码
# 用途：数据库用户的认证密码
# 默认值：'postgres' - 仅用于开发环境
# 安全建议：生产环境必须修改为强密码
TIMESCALEDB_PASSWORD = os.getenv('TIMESCALEDB_PASSWORD', 'postgres')

# 连接池配置
# 连接池用于复用数据库连接，减少连接建立开销，提升性能

# 连接池最小连接数
# 用途：连接池保持的最小活跃连接数
# 默认值：2
# 性能影响：过小会导致连接不足，过大会浪费资源
# 推荐值：小规模服务2-5，大规模服务5-10
TIMESCALEDB_POOL_MIN_SIZE = int(os.getenv('TIMESCALEDB_POOL_MIN_SIZE', '2'))

# 连接池最大连接数
# 用途：连接池允许的最大并发连接数
# 默认值：10
# 性能影响：决定了最大并发数据库操作数
# 推荐值：根据工作线程数和并发需求调整，通常为工作线程数的1-2倍
# 注意：需要考虑数据库服务器的max_connections限制
TIMESCALEDB_POOL_MAX_SIZE = int(os.getenv('TIMESCALEDB_POOL_MAX_SIZE', '10'))

# 连接获取超时时间（秒）
# 用途：从连接池获取连接的最大等待时间
# 默认值：30.0秒
# 性能影响：超时过短可能导致高负载时获取连接失败，过长会延长错误响应时间
# 推荐值：根据业务容忍度调整，通常10-60秒
TIMESCALEDB_POOL_TIMEOUT = float(os.getenv('TIMESCALEDB_POOL_TIMEOUT', '30.0'))

# 连接最大生命周期（秒）
# 用途：单个连接的最长存活时间，超时后会被回收重建
# 默认值：3600秒（1小时）
# 作用：防止长时间连接导致的内存泄漏或状态异常
# 推荐值：1800-7200秒，根据数据库服务器配置调整
TIMESCALEDB_POOL_MAX_LIFETIME = int(os.getenv('TIMESCALEDB_POOL_MAX_LIFETIME', '3600'))

# 连接最大空闲时间（秒）
# 用途：连接空闲多久后会被回收
# 默认值：600秒（10分钟）
# 作用：在低负载时减少不必要的连接，节省资源
# 推荐值：300-1800秒，业务活跃时可适当增大
TIMESCALEDB_POOL_MAX_IDLE = int(os.getenv('TIMESCALEDB_POOL_MAX_IDLE', '600'))

# ============ 服务类型配置 ============
# 服务运行模式选择
# 用途：区分通用版（监控多个交易对）和HYPE专用版（仅监控HYPE/PURR）
# 默认值：'general' - 通用版本
# 可选值：
#   - 'general': 通用版，支持多个交易对，使用较大的队列和更多工作线程
#   - 'hype_purr': HYPE专用版，仅监控HYPE/PURR配对，使用较小队列和较少线程
# 影响范围：影响队列大小、工作线程数、相关系数阈值等多个配置项的选择
# 使用建议：资源有限或只关注特定交易对时使用'hype_purr'，否则使用'general'
SERVICE_TYPE = os.getenv('SERVICE_TYPE', 'general')  # 'general' 或 'hype_purr'

# ============ API 配置 ============
# Hyperliquid交易所API地址
# 用途：获取K线数据、交易对信息等市场数据的API端点
# 默认值：'https://api.hyperliquid.xyz/info' - Hyperliquid主网API
# 说明：通常不需要修改，除非：
#   1. 使用测试网进行开发测试
#   2. 使用自建的API代理服务
# 影响范围：所有与Hyperliquid交易所的数据交互
HYPERLIQUID_API_URL = os.getenv('HYPERLIQUID_API_URL', 'https://api.hyperliquid.xyz/info')

# ============ 通用服务配置 ============
# 默认基准交易对（用于配对交易分析）
# 用途：作为配对交易的基准资产，其他交易对将与它进行协整分析
# 默认值：'BTC/USDC:USDC' - 比特币永续合约
# 说明：通用版服务的默认基准，通常选择流动性最好、最具代表性的资产
# 影响范围：影响配对分析的基准选择，所有其他交易对将与此交易对配对
DEFAULT_BASE_SYMBOL = os.getenv('BASE_SYMBOL', 'BTC/USDC:USDC')

# 默认分析时间周期列表
# 用途：定义进行协整分析的多个时间框架
# 默认值：['5m', '1h', '4h'] - 5分钟、1小时、4小时三个周期
# 说明：多周期分析可以捕捉不同时间尺度的交易机会
# 影响范围：决定了数据采集和分析的时间粒度
# 调整建议：增加周期会增加计算量，但可能提高分析准确性
DEFAULT_TIMEFRAMES = ['5m', '1h', '4h']

# 默认K线数据批量获取大小
# 用途：从API或数据库批量获取K线数据时的单次请求数量
# 默认值：1000条
# 性能影响：较大的批次可以减少请求次数，但会增加单次请求时间和内存占用
# 推荐值：500-2000，根据API限制和网络状况调整
DEFAULT_BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))

# 默认批量操作超时时间（秒）
# 用途：批量获取数据时的最大等待时间
# 默认值：5.0秒
# 说明：超过此时间将放弃当前批次请求
# 推荐值：根据网络延迟和数据量调整，通常3-10秒
DEFAULT_BATCH_TIMEOUT = float(os.getenv('BATCH_TIMEOUT', '5.0'))

# ============ HYPE/PURR 专用配置 ============
# HYPE专用版的基准交易对
# 用途：HYPE/PURR配对分析的基准资产
# 固定值：'HYPE/USDC:USDC'
# 说明：HYPE专用版服务专门用于监控HYPE和PURR这两个交易对的配对关系
HYPE_BASE_SYMBOL = 'HYPE/USDC:USDC'

# HYPE专用版监控的交易对列表
# 用途：限定HYPE专用版服务分析的交易对范围
# 固定值：['HYPE/USDC:USDC', 'PURR/USDC:USDC']
# 说明：仅监控这两个交易对，资源消耗较小
HYPE_SYMBOLS = ['HYPE/USDC:USDC', 'PURR/USDC:USDC']

# HYPE版本专用的相关系数阈值
# 用途：过滤交易对的相关系数最低要求（HYPE专用版）
# 默认值：0.5（比通用版的0.6更宽松）
# 业务含义：相关系数>=0.5才认为两个资产具有配对交易价值
# 调整原因：HYPE/PURR配对较为特殊，使用更宽松的阈值以捕捉更多机会
# 影响范围：仅在SERVICE_TYPE='hype_purr'时生效，替代TARGET_CORR_THRESHOLD
# 调优建议：
#   - 提高阈值(0.6-0.7)：更严格的筛选，信号更可靠但机会更少
#   - 降低阈值(0.4-0.5)：更宽松的筛选，机会更多但可能增加假信号
HYPE_CORR_THRESHOLD = float(os.getenv('HYPE_CORR_THRESHOLD', '0.5'))

# ============ 队列配置 ============
# 队列用于在不同处理阶段之间传递数据，配置大小需要平衡内存占用和处理能力

# 通用版本队列配置（大规模多交易对监控）
# 适用场景：监控大量交易对，需要较大的缓冲能力
# 内存估算：假设每个队列项约1KB，总内存约 (10000+15000+10000) * 1KB ≈ 35MB
QUEUE_CONFIG_GENERAL = {
    # K线数据接收缓冲区大小
    # 用途：暂存从WebSocket接收的原始K线数据，等待聚合处理
    # 默认值：10000
    # 说明：接收速度快于处理速度时，数据会在此缓冲
    # 调优：如果频繁出现队列满告警，需要增大此值或增加处理线程
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE', '10000')),
    
    # 分析任务队列大小
    # 用途：存储待分析的交易对和周期组合任务
    # 默认值：15000
    # 说明：这是最大的队列，因为分析任务生成速度快于分析速度
    # 调优：监控交易对较多时应适当增大，避免丢失分析任务
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE', '15000')),
    
    # 分析结果缓冲区大小
    # 用途：暂存分析完成的结果，等待批量写入数据库
    # 默认值：10000
    # 说明：结果会批量写入数据库以提高效率
    # 调优：数据库写入较慢时可能需要增大此值
    'analysis_result_buffer_size': int(os.getenv('ANALYSIS_RESULT_BUFFER_SIZE', '10000'))
}

# HYPE专用版队列配置（小规模特定交易对监控）
# 适用场景：仅监控HYPE/PURR两个交易对，资源占用小
# 内存估算：约 (1000+1000+1000) * 1KB ≈ 3MB
# 性能优势：内存占用低，适合资源受限环境
QUEUE_CONFIG_HYPE = {
    # K线数据接收缓冲区大小（HYPE版）
    # 默认值：1000（通用版的1/10）
    # 说明：仅2个交易对，数据量小，小缓冲区即可满足需求
    'kline_buffer_size': int(os.getenv('KLINE_BUFFER_SIZE_HYPE', '1000')),
    
    # 分析任务队列大小（HYPE版）
    # 默认值：1000
    # 说明：任务量少，小队列足够
    'analysis_queue_size': int(os.getenv('ANALYSIS_QUEUE_SIZE_HYPE', '1000')),
    
    # 分析结果缓冲区大小（HYPE版）
    # 默认值：1000
    # 说明：结果数量少，小缓冲区即可
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