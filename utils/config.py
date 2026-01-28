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
# 数据充足性阈值 - 判断数据是否足够进行可靠分析

# 4小时周期最小数据点数
# 用途：4小时周期特定的数据充足性检查
# 默认值：358个数据点
# 对应时长：约358 * 4小时 = 1432小时 ≈ 60天
# 统计意义：确保有足够的历史数据进行长周期协整分析
# 说明：4小时周期用于长期趋势分析，需要更多历史数据
MIN_4H_DATA_POINTS = int(os.getenv('MIN_4H_DATA_POINTS', '358'))

# 通用最小数据点数
# 用途：其他周期的数据充足性基准（如5分钟、1小时）
# 默认值：100个数据点
# 统计意义：100个样本点通常被认为是统计分析的最小可靠样本量
# 说明：少于此数量的数据可能导致分析结果不稳定
MIN_DATA_POINTS = int(os.getenv('MIN_DATA_POINTS', '100'))

# 数据验证最小点数（用于各个分析算法）
# 这些阈值确保各个统计算法有足够的数据进行计算

# 相关系数计算最小数据点数
# 用途：计算Pearson相关系数所需的最小样本量
# 默认值：20个数据点
# 统计意义：相关系数计算对样本量要求相对较低，20个点可以给出初步评估
# 说明：样本量过小会导致相关系数不稳定，容易受异常值影响
MIN_POINTS_FOR_CORRELATION = int(os.getenv('MIN_POINTS_FOR_CORRELATION', '20'))

# 协整检验最小数据点数
# 用途：执行ADF（增强迪基-富勒）协整检验所需的最小样本量
# 默认值：30个数据点
# 统计意义：协整检验是时间序列检验，需要更多数据才能获得可靠结果
# 说明：这是协整分析的核心检验，数据不足会导致检验无效
MIN_POINTS_FOR_COINTEGRATION = int(os.getenv('MIN_POINTS_FOR_COINTEGRATION', '30'))

# Z-score计算最小数据点数
# 用途：计算价差Z-score（标准化偏离度）所需的最小样本量
# 默认值：19个数据点
# 统计意义：需要足够样本来计算均值和标准差
# 说明：Z-score用于判断价差是否偏离正常范围，是交易信号的关键指标
MIN_POINTS_FOR_ZSCORE = int(os.getenv('MIN_POINTS_FOR_ZSCORE', '19'))

# 相关系数过滤阈值（关键参数）
# 用途：筛选具有配对交易价值的交易对组合
# 默认值：0.6（通用版）
# 统计意义：
#   - 0.6-0.8：中等到较强的正相关
#   - >0.8：强正相关
#   - <0.6：相关性较弱，配对交易风险较大
# 业务含义：只有相关系数>=0.6的交易对才会进入后续的协整分析
# 影响范围：这是第一道过滤器，直接决定了哪些交易对会被分析
# 调优建议：
#   - 提高(0.7-0.8)：更保守，减少假信号，但可能错过一些机会
#   - 降低(0.5-0.6)：更激进，捕捉更多机会，但需要承担更多风险
# 注意：HYPE 版本会使用 HYPE_CORR_THRESHOLD (0.5) 而非此默认值
TARGET_CORR_THRESHOLD = float(os.getenv('TARGET_CORR_THRESHOLD', '0.6'))

# 协整检验显著性水平
# 用途：ADF协整检验的p-value阈值
# 默认值：0.05（5%显著性水平）
# 统计意义：
#   - p-value < 0.05：拒绝原假设，认为存在协整关系（95%置信度）
#   - p-value >= 0.05：不能拒绝原假设，不存在显著协整关系
# 业务含义：只有通过协整检验的交易对才具有统计套利价值
# 调优建议：
#   - 降低(0.01)：更严格，要求99%置信度，信号更可靠但更少
#   - 提高(0.1)：更宽松，要求90%置信度，信号更多但可能增加假阳性
COINTEGRATION_SIGNIFICANCE_LEVEL = float(os.getenv('COINTEGRATION_SIGNIFICANCE_LEVEL', '0.05'))

# 数据窗口配置（天数）
# 用途：定义各个时间周期回溯获取的历史数据长度
# 影响：更长的窗口提供更多历史数据，但增加计算和存储成本
DATA_WINDOW_CONFIG = {
    # 5分钟周期数据窗口
    # 默认值：7天
    # 数据点数：7 * 24 * 60 / 5 = 2016个数据点
    # 用途：短期交易信号，捕捉日内波动
    '5m': int(os.getenv('DATA_WINDOW_5M', '7')),
    
    # 1小时周期数据窗口
    # 默认值：30天
    # 数据点数：30 * 24 = 720个数据点
    # 用途：中期趋势分析，捕捉周级别的交易机会
    '1h': int(os.getenv('DATA_WINDOW_1H', '30')),
    
    # 4小时周期数据窗口
    # 默认值：60天
    # 数据点数：60 * 24 / 4 = 360个数据点
    # 用途：长期趋势分析，捕捉月级别的结构性机会
    '4h': int(os.getenv('DATA_WINDOW_4H', '60'))
}

# 分析算法参数

# Beta系数计算窗口
# 用途：滚动窗口计算配对交易中的对冲比率(Beta)
# 默认值：100个数据点
# 统计意义：Beta = Cov(Y,X) / Var(X)，表示Y相对于X的敏感度
# 业务含义：Beta值决定了配对交易时的头寸比例
# 调优建议：
#   - 增大(150-200)：Beta更稳定但反应滞后，适合长期持仓
#   - 减小(50-80)：Beta更灵敏但可能波动大，适合短期交易
BETA_WINDOW = int(os.getenv('BETA_WINDOW', '100'))

# Z-score计算窗口
# 用途：计算价差标准化偏离度的滚动窗口
# 默认值：30个数据点
# 统计意义：Z-score = (当前价差 - 均值) / 标准差
# 业务含义：Z-score > 2或< -2通常被认为是交易信号
# 调优建议：
#   - 增大(40-60)：Z-score更平滑，减少假信号
#   - 减小(20-30)：Z-score更敏感，捕捉更多交易机会
ZSCORE_WINDOW = int(os.getenv('ZSCORE_WINDOW', '30'))

# 协整检验阈值（已弃用？）
# 注意：此参数名称可能有歧义，实际用途需要查看代码确认
# 默认值：2
# 说明：可能是某种分级判断标准，具体含义需要结合代码逻辑
COINTEGRATION_THRESHOLD = int(os.getenv('COINTEGRATION_THRESHOLD', '2'))

# Z-score交易信号阈值
# 用途：根据Z-score值判断开仓时机的阈值设置
# 说明：不同的阈值对应不同的交易策略
ZSCORE_THRESHOLDS = {
    # 做多信号阈值（Z-score的负向阈值）
    # 默认值：0.2
    # 含义：当Z-score < -0.2时可能考虑做多价差（买入低估资产）
    # 说明：较小的阈值意味着更频繁的交易信号
    'long': float(os.getenv('ZSCORE_THRESHOLD_LONG', '0.2')),
    
    # 中性信号阈值
    # 默认值：1.5
    # 含义：Z-score在±1.5之间认为价差处于正常范围
    # 用途：可能用于判断是否平仓或继续持有
    'middle': float(os.getenv('ZSCORE_THRESHOLD_MIDDLE', '1.5')),
    
    # 做空信号阈值（Z-score的正向阈值）
    # 默认值：1.8
    # 含义：当Z-score > 1.8时可能考虑做空价差（卖出高估资产）
    # 说明：此值略高于middle，可能用于判断强信号
    'short': float(os.getenv('ZSCORE_THRESHOLD_SHORT', '1.8'))
}

# ============ 去重配置 ============
# 去重机制用于防止短时间内对同一交易对和周期进行重复分析，节省计算资源

# 入队去重窗口（秒）
# 用途：控制同一分析任务的入队频率，防止队列中出现大量重复任务
# 机制：在指定时间窗口内，相同的(交易对, 周期)组合只能入队一次
# 影响范围：影响分析任务的生成频率，不影响已入队任务的执行
ENQUEUE_DEDUP_WINDOWS = {
    # 5分钟周期入队去重窗口
    # 默认值：30秒
    # 含义：同一5分钟周期的分析任务，30秒内只能入队一次
    # 说明：5分钟周期数据更新频繁，但不需要每次K线都触发分析
    '5m': int(os.getenv('ENQUEUE_DEDUP_5M', '30')),
    
    # 1小时周期入队去重窗口
    # 默认值：180秒（3分钟）
    # 含义：同一1小时周期的分析任务，3分钟内只能入队一次
    # 说明：1小时周期变化较慢，3分钟去重窗口可以有效减少重复
    '1h': int(os.getenv('ENQUEUE_DEDUP_1H', '180')),
    
    # 4小时周期入队去重窗口
    # 默认值：600秒（10分钟）
    # 含义：同一4小时周期的分析任务，10分钟内只能入队一次
    # 说明：4小时周期变化最慢，较长的去重窗口可以大幅减少任务量
    '4h': int(os.getenv('ENQUEUE_DEDUP_4H', '600'))
}

# 分析去重窗口（秒）
# 用途：控制实际执行分析的频率，避免短时间内重复分析相同数据
# 机制：即使任务已入队，如果上次分析时间在去重窗口内，也会跳过本次分析
# 区别：这是执行层面的去重，比入队去重更严格
DEDUP_WINDOWS = {
    # 5分钟周期分析去重窗口
    # 默认值：60秒（1分钟）
    # 含义：同一5分钟周期的分析，1分钟内只能执行一次
    # 说明：比入队窗口(30秒)更长，提供双重保护
    '5m': int(os.getenv('DEDUP_5M', '60')),
    
    # 1小时周期分析去重窗口
    # 默认值：300秒（5分钟）
    # 含义：同一1小时周期的分析，5分钟内只能执行一次
    '1h': int(os.getenv('DEDUP_1H', '300')),
    
    # 4小时周期分析去重窗口
    # 默认值：900秒（15分钟）
    # 含义：同一4小时周期的分析，15分钟内只能执行一次
    # 说明：4小时周期K线更新缓慢，15分钟去重可以大幅降低计算负担
    '4h': int(os.getenv('DEDUP_4H', '900'))
}

# 去重记录清理间隔（秒）
# 用途：定期清理过期的去重记录，防止内存无限增长
# 默认值：300秒（5分钟）
# 说明：每5分钟清理一次过期的去重key，释放内存
# 调优：根据系统内存和去重记录数量调整，通常不需要修改
CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '300'))

# 最近任务记录数上限
# 用途：限制内存中保留的最近任务记录数量
# 默认值：5000条
# 内存估算：假设每条记录100字节，约500KB内存
# 说明：用于任务追踪和去重检查，超过上限的旧记录会被移除
# 调优：监控交易对较多时可以适当增大
MAX_RECENT_TASKS = int(os.getenv('MAX_RECENT_TASKS', '5000'))

# ============ WebSocket 配置 ============
# WebSocket用于实时接收交易所的K线数据流

# WebSocket连接超时时间（秒）
# 用途：WebSocket连接建立和消息接收的超时限制
# 默认值：30秒
# 说明：超过此时间未收到数据或心跳，连接将被视为失败
# 调优建议：
#   - 网络不稳定环境：可以适当增大到45-60秒
#   - 需要快速故障检测：可以减小到15-20秒
WS_TIMEOUT = int(os.getenv('WS_TIMEOUT', '30'))

# WebSocket最大重连次数
# 用途：连接断开后的最大重试次数
# 默认值：30次
# 说明：达到最大次数后仍失败，将触发告警并可能停止服务
# 重连策略：通常配合指数退避，避免频繁重连
# 调优：稳定环境可以减小到10-15次，测试环境可以设为更大值
WS_MAX_RETRIES = int(os.getenv('WS_MAX_RETRIES', '30'))

# WebSocket连接异常告警阈值
# 用途：短时间内连续失败多少次后触发告警通知
# 默认值：5次
# 说明：避免偶发性网络抖动导致的告警轰炸
# 业务含义：连续失败5次通常表示网络或API服务存在严重问题
# 调优：对可靠性要求高的环境可以设为2-3次
WS_ALERT_THRESHOLD = int(os.getenv('WS_ALERT_THRESHOLD', '5'))

# ============ 工作线程配置 ============
# 工作线程用于并发执行协整分析任务，数量影响系统并发处理能力

# 通用版本工作线程数
# 用途：执行配对交易分析的并发工作线程数（通用版）
# 默认值：15个线程
# 性能影响：
#   - CPU利用率：每个线程占用约5-10% CPU（取决于分析复杂度）
#   - 总CPU占用：约75-150%（可能使用多核）
#   - 吞吐量：约每秒可处理15-30个分析任务（取决于数据量）
# 调优建议：
#   - 根据CPU核心数调整：推荐值 = CPU核心数 * 1.5-2
#   - 4核CPU：8-12个线程
#   - 8核CPU：12-16个线程
#   - 16核CPU：20-30个线程
# 注意：过多线程会导致上下文切换开销，反而降低性能
ANALYSIS_WORKERS_GENERAL = int(os.getenv('ANALYSIS_WORKERS', '15'))

# HYPE专用版工作线程数
# 用途：执行配对交易分析的并发工作线程数（HYPE专用版）
# 默认值：2个线程
# 说明：HYPE版本仅监控2个交易对，任务量小，2个线程足够
# 资源优势：CPU占用低（约10-20%），适合与其他服务共享资源
# 调优：通常不需要调整，除非发现分析延迟较大
ANALYSIS_WORKERS_HYPE = int(os.getenv('ANALYSIS_WORKERS_HYPE', '2'))

# ============ 批量写入配置 ============
# 批量写入用于优化数据库性能，将多条分析结果合并成一次写入操作

# 分析结果批量写入大小
# 用途：累积多少条分析结果后执行一次批量写入
# 默认值：100条
# 性能影响：
#   - 批量大：减少数据库写入次数，提高吞吐量，但增加数据延迟
#   - 批量小：降低数据延迟，但增加数据库写入次数
# 权衡建议：
#   - 高吞吐场景：200-500条，优先考虑性能
#   - 低延迟场景：50-100条，优先考虑实时性
# 内存影响：假设每条结果1KB，100条占用约100KB内存
ANALYSIS_RESULT_BATCH_SIZE = int(os.getenv('ANALYSIS_RESULT_BATCH_SIZE', '100'))

# 分析结果批量写入超时时间（秒）
# 用途：即使未达到批量大小，超过此时间也会强制写入
# 默认值：2.0秒
# 作用：防止在低流量时段数据长时间积压在内存中
# 业务含义：保证分析结果最多延迟2秒就会写入数据库
# 调优建议：
#   - 实时性要求高：0.5-1.0秒
#   - 性能优先：3.0-5.0秒
ANALYSIS_RESULT_BATCH_TIMEOUT = float(os.getenv('ANALYSIS_RESULT_BATCH_TIMEOUT', '2.0'))

# 是否使用COPY批量写入方法
# 用途：选择数据库批量写入的实现方式
# 默认值：false（使用INSERT VALUES方法）
# 可选方法：
#   - false: 使用 INSERT INTO ... VALUES (...), (...), ... 
#     - 优点：兼容性好，支持RETURNING子句
#     - 缺点：大批量时性能较差
#   - true: 使用 COPY ... FROM STDIN
#     - 优点：大批量写入性能极佳（比INSERT快5-10倍）
#     - 缺点：不支持RETURNING，错误处理较复杂
# 推荐使用场景：
#   - COPY：批量大小>500或写入频率极高
#   - INSERT：批量较小或需要获取插入后的ID
ANALYSIS_USE_COPY_METHOD = os.getenv('ANALYSIS_USE_COPY_METHOD', 'false').lower() in ('true', '1', 'yes')

# ============ 监控配置 ============
# 系统运行状态监控相关配置

# 队列监控检查间隔（秒）
# 用途：多久检查一次各个队列的使用情况
# 默认值：60秒（1分钟）
# 说明：定期检查队列使用率，当超过阈值时发出告警
# 监控内容：kline_buffer、analysis_queue、analysis_result_buffer的使用率
# 调优：
#   - 更频繁监控：30秒，更快发现问题
#   - 降低开销：120-300秒，减少监控开销
QUEUE_MONITOR_INTERVAL = int(os.getenv('QUEUE_MONITOR_INTERVAL', '60'))

# 队列使用率告警阈值
# 用途：队列使用率超过此比例时触发告警
# 默认值：0.8（80%）
# 计算方式：告警阈值 = 当前队列大小 / 最大队列容量
# 业务含义：
#   - >=80%：队列接近饱和，需要关注
#   - >=90%：队列严重拥堵，可能导致数据丢失
#   - <80%：队列健康
# 告警作用：提前预警，避免队列溢出导致数据丢失
# 调优建议：
#   - 提高(0.85-0.9)：减少告警频率，但风险窗口更小
#   - 降低(0.7-0.75)：更早发现问题，但可能产生更多告警
QUEUE_WARNING_THRESHOLD = float(os.getenv('QUEUE_WARNING_THRESHOLD', '0.8'))

# ============ 日志配置 ============
# 注意：这些配置主要在 utils/logging_config.py 中使用
# 在此处定义是为了统一管理所有配置项

# 单个日志文件最大大小（字节）
# 用途：日志文件达到此大小后会自动轮转（创建新文件）
# 默认值：100MB (100 * 1024 * 1024 字节)
# 说明：避免单个日志文件过大，影响查看和传输
# 推荐值：
#   - 开发环境：50-100MB
#   - 生产环境：100-500MB
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(100 * 1024 * 1024)))  # 100MB

# 日志文件保留数量
# 用途：最多保留多少个历史日志文件
# 默认值：5个
# 存储占用：5个 * 100MB = 500MB
# 说明：超过此数量的旧日志文件会被自动删除
# 时间跨度：根据日志生成速度，通常可以覆盖几天到几周的历史
# 调优建议：
#   - 磁盘空间充足：10-20个，保留更长历史
#   - 磁盘空间有限：3-5个，仅保留近期日志
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))

# ============ OLS 协整分析参数 ============
# OLS (Ordinary Least Squares，普通最小二乘法) 用于建立配对交易的线性回归模型

# OLS回归最小数据点数
# 用途：执行OLS线性回归所需的最小样本量
# 默认值：10个数据点
# 统计意义：回归分析至少需要自由度>0，即样本量>参数量
# 说明：一元线性回归有2个参数(截距α和斜率β)，理论上最小需要3个点
#       但实际需要更多样本才能获得可靠的回归结果
# 调优：样本太少会导致回归不稳定，建议至少保持10-20个点
MIN_POINTS_FOR_OLS = int(os.getenv('MIN_POINTS_FOR_OLS', '10'))

# 健康监控最小数据点数
# 用途：执行策略健康度评估所需的最小历史数据量
# 默认值：200个数据点
# 业务含义：健康监控需要足够长的历史窗口来评估策略稳定性
# 说明：对应的时间长度取决于周期（如4h周期对应约33天）
# 调优：减小会降低评估准确性，增大会延长冷启动时间
MIN_POINTS_FOR_HEALTH_MONITOR = int(os.getenv('MIN_POINTS_FOR_HEALTH_MONITOR', '200'))

# 协整模型选择阈值
# 用于判断应该使用哪种协整模型（带截距或不带截距）

# Alpha显著性水平（截距项t检验）
# 用途：判断回归截距α是否显著不为0的p-value阈值
# 默认值：0.05（5%显著性水平）
# 统计含义：
#   - p-value < 0.05：α显著不为0，应使用带截距模型
#   - p-value >= 0.05：α不显著，可以使用无截距模型
# 业务影响：模型选择影响价差计算和交易信号
ALPHA_SIGNIFICANCE_LEVEL = float(os.getenv('ALPHA_SIGNIFICANCE_LEVEL', '0.05'))

# 跨资产Alpha阈值（绝对值）
# 用途：判断不同资产间配对的截距是否过大
# 默认值：5
# 业务含义：如果|α| > 5，说明两个资产存在较大的系统性价差
# 说明：跨资产配对（如BTC vs ETH）通常允许较大的α值
# 影响：超过此阈值可能影响模型选择或风险评估
ALPHA_CROSS_ASSET_THRESHOLD = float(os.getenv('ALPHA_CROSS_ASSET_THRESHOLD', '5'))

# 同资产Alpha阈值（绝对值）
# 用途：判断同资产不同合约的截距是否过大
# 默认值：2
# 业务含义：同一资产的不同合约（如现货vs永续）理论上α应接近0
# 说明：|α| > 2说明可能存在基差或资金费率影响
# 风险提示：同资产配对α过大可能表示套利机会有限
ALPHA_SAME_ASSET_THRESHOLD = float(os.getenv('ALPHA_SAME_ASSET_THRESHOLD', '2'))

# ============ 信号强度阈值 ============
# 用于判断交易信号的强弱程度，帮助区分交易机会的质量

# 强信号Z-score阈值
# 用途：判断是否为"强"交易信号的Z-score绝对值标准
# 默认值：2.5
# 统计意义：|Z-score| > 2.5对应约99%的置信区间外（正态分布假设）
# 业务含义：价差偏离均值超过2.5个标准差，是非常强的均值回归信号
# 交易策略：强信号通常对应较大的交易头寸或更积极的入场
# 调优建议：
#   - 保守型：3.0（更少但更可靠的信号）
#   - 激进型：2.0（更多但风险更高的信号）
ZSCORE_STRONG_THRESHOLD = float(os.getenv('ZSCORE_STRONG_THRESHOLD', '2.5'))

# 中等信号Z-score阈值
# 用途：判断是否为"中等"交易信号的Z-score绝对值标准
# 默认值：2.0
# 统计意义：|Z-score| > 2.0对应约95%的置信区间外
# 业务含义：价差偏离均值超过2个标准差，是较强的交易信号
# 信号分级：
#   - |Z-score| > 2.5：强信号
#   - 2.0 < |Z-score| <= 2.5：中等信号
#   - |Z-score| <= 2.0：弱信号或观察状态
ZSCORE_MEDIUM_THRESHOLD = float(os.getenv('ZSCORE_MEDIUM_THRESHOLD', '2.0'))

# ============ 健康监控参数 ============
# 策略健康度监控用于评估配对交易策略的长期稳定性和可靠性

# 健康监控长窗口大小
# 用途：计算长期健康得分的数据窗口
# 默认值：200个数据点
# 时间跨度：对于4h周期约33天，1h周期约8天
# 业务含义：反映策略的长期表现和稳定性
# 用途：作为基准窗口，与短窗口对比评估策略状态变化
HEALTH_MONITOR_LONG_WINDOW = int(os.getenv('HEALTH_MONITOR_LONG_WINDOW', '200'))

# 健康监控短窗口大小
# 用途：计算短期健康得分的数据窗口
# 默认值：100个数据点
# 时间跨度：对于4h周期约17天，1h周期约4天
# 业务含义：反映策略的近期表现
# 对比分析：短期得分显著低于长期得分，说明策略近期恶化
HEALTH_MONITOR_SHORT_WINDOW = int(os.getenv('HEALTH_MONITOR_SHORT_WINDOW', '100'))

# 健康状态分级阈值
# 用途：根据健康得分划分策略的健康等级
# 默认值：(18, 14, 10) - 三个临界点
# 状态分级：
#   - 得分 >= 18：HEALTHY（健康）- 策略状态良好，可以正常交易
#   - 14 <= 得分 < 18：WARNING（警告）- 策略表现下降，需要密切关注
#   - 10 <= 得分 < 14：DANGER（危险）- 策略严重恶化，考虑暂停交易
#   - 得分 < 10：CRITICAL（严重）- 策略失效，应立即停止交易
# 评分依据：综合考虑协整性、相关性、Hurst指数、Beta稳定性等多个指标
# 调优建议：根据实际策略表现和风险承受能力调整阈值
HEALTH_MONITOR_STATE_THRESHOLDS = tuple(map(int, os.getenv('HEALTH_MONITOR_STATE_THRESHOLDS', '18,14,10').split(',')))

# 健康监控周期配置
# 用途：指定健康监控使用的时间周期和数据窗口
# 默认值：('4h', '60d') - 4小时周期，60天数据
# 格式：(时间周期, 数据窗口天数)
# 说明：
#   - 4h：4小时K线，适合捕捉中长期趋势
#   - 60d：60天历史数据，提供充足的统计样本
# 业务含义：健康监控关注长期稳定性，因此使用较长周期
# 调优：可以修改为 '1h,30d' 或 '1d,90d' 等组合
HEALTH_MONITOR_PERIOD = tuple(os.getenv('HEALTH_MONITOR_PERIOD', '4h,60d').split(','))

# ============ 多周期分析配置 ============
# 多周期分析要求在多个时间框架上都通过协整检验，提高信号可靠性

# 必需分析周期列表
# 用途：定义必须进行分析的时间周期和对应的数据窗口
# 默认值：[('5m', '7d'), ('1h', '30d'), ('4h', '60d')]
# 格式：[(周期1, 窗口1), (周期2, 窗口2), ...]
# 说明：
#   - '5m', '7d'：5分钟周期，使用7天历史数据
#   - '1h', '30d'：1小时周期，使用30天历史数据
#   - '4h', '60d'：4小时周期，使用60天历史数据
# 业务逻辑：
#   - 只有在所有周期都显示协整关系时，才认为配对可靠
#   - 多周期验证可以过滤掉偶然的假信号
#   - 不同周期捕捉不同时间尺度的交易机会
# 数据量要求：
#   - 5m/7d：约2016个数据点
#   - 1h/30d：约720个数据点
#   - 4h/60d：约360个数据点
# 环境变量格式：'5m,7d;1h,30d;4h,60d'（用分号分隔周期组，逗号分隔周期和窗口）
REQUIRED_PERIODS = [
    tuple(p.split(',')) for p in os.getenv('REQUIRED_PERIODS', '5m,7d;1h,30d;4h,60d').split(';')
]

# ============ 告警格式化配置 ============
# 告警格式化模块用于将分析结果转化为易读的告警消息，并进行风险分级

# -------- 信号强度判断阈值 --------
# 用于评估交易信号的强度等级，基于多周期Z-score的综合表现

# 极强信号阈值
# 用途：判断是否为"极强"交易信号
# 默认值：1.5
# 计算方式：基于多周期Z-score的加权平均或最大值
# 业务含义：
#   - 信号强度 > 1.5：极强信号，多个周期同时出现强烈偏离
#   - 交易建议：可以考虑较大仓位或积极入场
# 告警显示：通常用红色或高优先级标记
ALERT_SIGNAL_STRENGTH_EXTREME = float(os.getenv('ALERT_SIGNAL_STRENGTH_EXTREME', '1.5'))

# 强信号阈值
# 用途：判断是否为"强"交易信号
# 默认值：1.0
# 业务含义：
#   - 1.0 < 信号强度 <= 1.5：强信号，值得关注
#   - 交易建议：可以考虑中等仓位入场
ALERT_SIGNAL_STRENGTH_STRONG = float(os.getenv('ALERT_SIGNAL_STRENGTH_STRONG', '1.0'))

# 中等信号阈值
# 用途：判断是否为"中等"交易信号
# 默认值：0.5
# 业务含义：
#   - 0.5 < 信号强度 <= 1.0：中等信号，需要结合其他指标判断
#   - 信号强度 <= 0.5：弱信号，谨慎参考
# 告警显示：中等信号通常用黄色标记
ALERT_SIGNAL_STRENGTH_MEDIUM = float(os.getenv('ALERT_SIGNAL_STRENGTH_MEDIUM', '0.5'))

# -------- 信号质量评估阈值（基于协整通过数量）--------
# 通过的协整检验越多，说明配对关系在多个周期上都得到验证，信号质量越高

# 优秀质量阈值
# 用途：判断信号质量是否达到"优秀"级别
# 默认值：5个周期通过协整检验
# 业务含义：在5个以上时间周期都通过协整检验，配对关系非常稳定
# 说明：如果分析3个周期，此阈值可能永远无法达到，需要根据实际周期数调整
ALERT_QUALITY_EXCELLENT = int(os.getenv('ALERT_QUALITY_EXCELLENT', '5'))

# 良好质量阈值
# 用途：判断信号质量是否达到"良好"级别
# 默认值：4个周期通过协整检验
# 业务含义：在4个时间周期通过协整检验，配对关系较为可靠
ALERT_QUALITY_GOOD = int(os.getenv('ALERT_QUALITY_GOOD', '4'))

# 一般质量阈值
# 用途：判断信号质量是否达到"一般"级别
# 默认值：3个周期通过协整检验
# 业务含义：
#   - >= 3个周期通过：一般质量，基本可用
#   - < 3个周期通过：质量较差，需谨慎对待
ALERT_QUALITY_FAIR = int(os.getenv('ALERT_QUALITY_FAIR', '3'))

# -------- 相关系数评级阈值 --------
# 相关系数反映两个资产价格走势的线性相关程度

# 相关系数优秀阈值
# 用途：判断相关系数是否达到"优秀"水平
# 默认值：0.8
# 统计含义：相关系数 >= 0.8表示强正相关
# 业务含义：两个资产价格走势高度一致，配对交易基础牢固
# 告警显示：通常用绿色标记，表示配对质量很好
ALERT_CORR_EXCELLENT = float(os.getenv('ALERT_CORR_EXCELLENT', '0.8'))

# 相关系数良好阈值
# 用途：判断相关系数是否达到"良好"水平
# 默认值：0.6
# 统计含义：0.6 <= 相关系数 < 0.8表示中等到较强正相关
# 业务含义：两个资产有明显的同步走势，适合配对交易
# 告警显示：通常用黄色标记
# 分级逻辑：
#   - >= 0.8：优秀（绿色）
#   - 0.6-0.8：良好（黄色）
#   - < 0.6：一般或较差（可能不显示或用灰色）
ALERT_CORR_GOOD = float(os.getenv('ALERT_CORR_GOOD', '0.6'))

# -------- Hurst指数判断阈值 --------
# Hurst指数用于判断时间序列的记忆性和均值回复特性

# Hurst趋势阈值
# 用途：判断价差序列是否具有趋势性
# 默认值：0.6
# 统计含义：
#   - Hurst > 0.6：趋势性序列，有长期记忆效应
#   - Hurst = 0.5：随机游走
#   - Hurst < 0.5：均值回复序列
# 业务含义：Hurst > 0.6说明价差有趋势，不适合均值回复策略
# 风险提示：高Hurst值的配对需谨慎，可能不会快速回归
ALERT_HURST_TREND = float(os.getenv('ALERT_HURST_TREND', '0.6'))

# Hurst均值回复阈值
# 用途：判断价差序列是否具有均值回复特性
# 默认值：0.4
# 统计含义：Hurst < 0.4表示强均值回复特性
# 业务含义：价差偏离后倾向于快速回归，理想的配对交易特征
# 告警显示：低Hurst值通常是有利因素，可能用绿色标记
# 分级逻辑：
#   - Hurst < 0.4：强均值回复（有利）
#   - 0.4 <= Hurst <= 0.6：中性或弱均值回复
#   - Hurst > 0.6：趋势性（不利）
ALERT_HURST_MEAN_REVERSION = float(os.getenv('ALERT_HURST_MEAN_REVERSION', '0.4'))

# -------- 健康监控窗口对比阈值 --------
# 通过对比长短期健康得分，判断策略稳定性变化

# 得分差异过大阈值
# 用途：判断长短期健康得分差异是否过大
# 默认值：15分
# 业务含义：长期得分 - 短期得分 > 15，说明策略近期显著恶化
# 风险提示：大幅恶化可能预示配对关系破裂，需要警惕
ALERT_SCORE_DIFF_HIGH = int(os.getenv('ALERT_SCORE_DIFF_HIGH', '15'))

# 得分差异需关注阈值
# 用途：判断长短期健康得分差异是否需要关注
# 默认值：10分
# 业务含义：10 < 得分差异 <= 15，策略有恶化趋势，需要监控
ALERT_SCORE_DIFF_MEDIUM = int(os.getenv('ALERT_SCORE_DIFF_MEDIUM', '10'))

# 短期恶化判断阈值
# 用途：单独判断短期得分是否显著下降
# 默认值：5分
# 业务含义：短期得分比长期得分低5分以上，可能是暂时性波动
# 说明：此阈值低于MEDIUM，用于早期预警
ALERT_SCORE_DETERIORATE = int(os.getenv('ALERT_SCORE_DETERIORATE', '5'))

# -------- 风险评估 - 高风险因素阈值 --------
# 识别高风险配对，这些因素可能导致交易失败或巨额亏损

# 高风险：最低得分阈值
# 用途：健康得分低于此值视为高风险因素
# 默认值：10分
# 业务含义：得分 < 10表示策略健康度严重不足（对应DANGER/CRITICAL状态）
# 风险提示：低得分配对应避免交易或快速止损
ALERT_RISK_HIGH_SCORE_MIN = int(os.getenv('ALERT_RISK_HIGH_SCORE_MIN', '10'))

# 高风险：得分差异阈值
# 用途：长短期得分差异超过此值视为高风险因素
# 默认值：15分
# 业务含义：策略近期急剧恶化，可能已经失效
# 风险提示：大幅恶化通常需要立即平仓或停止新开仓
ALERT_RISK_HIGH_SCORE_DIFF = int(os.getenv('ALERT_RISK_HIGH_SCORE_DIFF', '15'))

# 高风险：Hurst阈值
# 用途：Hurst指数超过此值视为高风险因素
# 默认值：0.7
# 业务含义：Hurst > 0.7说明价差有强趋势性，均值回复策略高风险
# 风险提示：高Hurst配对可能导致价差持续扩大，不会回归
ALERT_RISK_HIGH_HURST = float(os.getenv('ALERT_RISK_HIGH_HURST', '0.7'))

# -------- 风险评估 - 中等风险因素阈值 --------
# 识别中等风险因素，需要谨慎对待但不一定禁止交易

# 中风险：协整最低通过数
# 用途：协整通过周期少于此值视为中等风险
# 默认值：3个周期
# 业务含义：通过周期 < 3说明配对关系验证不充分
# 风险提示：协整检验通过较少，配对可靠性存疑
ALERT_RISK_MID_COINT_MIN = int(os.getenv('ALERT_RISK_MID_COINT_MIN', '3'))

# 中风险：Z-score倍数（短周期/长周期）
# 用途：短期Z-score是长期Z-score的多少倍视为中等风险
# 默认值：3倍
# 业务含义：短期偏离远大于长期，可能是短期过度反应
# 风险提示：需要判断是真实机会还是噪声信号
ALERT_RISK_MID_ZSCORE_RATIO = int(os.getenv('ALERT_RISK_MID_ZSCORE_RATIO', '3'))

# 中风险：得分阈值（WARNING/DANGER状态）
# 用途：健康得分低于此值但未达到高风险视为中等风险
# 默认值：18分
# 业务含义：14 <= 得分 < 18对应WARNING状态，需要关注
ALERT_RISK_MID_SCORE_MIN = int(os.getenv('ALERT_RISK_MID_SCORE_MIN', '18'))

# 中风险：β变异系数阈值
# 用途：Beta系数的变异系数（标准差/均值）超过此值视为中等风险
# 默认值：0.2（20%）
# 业务含义：Beta不稳定，对冲比率波动大，增加执行风险
# 风险提示：Beta波动大可能导致对冲失效
ALERT_RISK_MID_BETA_CV = float(os.getenv('ALERT_RISK_MID_BETA_CV', '0.2'))

# -------- 风险评估 - 有利因素阈值 --------
# 识别有利因素，这些特征增加交易成功概率

# 有利因素：健康得分阈值
# 用途：健康得分超过此值视为有利因素
# 默认值：18分
# 业务含义：得分 >= 18表示策略健康（对应HEALTHY状态）
# 告警显示：通常用绿色标记，鼓励交易
ALERT_RISK_GREEN_SCORE_MIN = int(os.getenv('ALERT_RISK_GREEN_SCORE_MIN', '18'))

# 有利因素：相关系数阈值
# 用途：相关系数超过此值视为有利因素
# 默认值：0.6
# 业务含义：相关性良好或优秀，配对基础稳固
ALERT_RISK_GREEN_CORR_MIN = float(os.getenv('ALERT_RISK_GREEN_CORR_MIN', '0.6'))

# 有利因素：协整通过数阈值
# 用途：协整通过周期数超过此值视为有利因素
# 默认值：4个周期
# 业务含义：在4个以上周期通过协整检验，配对关系充分验证
ALERT_RISK_GREEN_COINT_MIN = int(os.getenv('ALERT_RISK_GREEN_COINT_MIN', '4'))

# -------- 综合评级判断阈值 --------
# 根据高风险、中风险、有利因素的数量进行综合评级

# 评级：高风险数量阈值
# 用途：高风险因素数量达到此值时，给予较低综合评级
# 默认值：2个
# 业务含义：>= 2个高风险因素，配对不建议交易
# 评级结果：可能评为D级或E级（最低级）
ALERT_RATING_HIGH_COUNT = int(os.getenv('ALERT_RATING_HIGH_COUNT', '2'))

# 评级：中风险数量阈值
# 用途：中风险因素数量达到此值时，降低综合评级
# 默认值：2个
# 业务含义：>= 2个中风险因素，配对需谨慎对待
# 评级结果：可能评为C级或B级（中等）
ALERT_RATING_MID_COUNT = int(os.getenv('ALERT_RATING_MID_COUNT', '2'))

# 评级：有利因素数量阈值
# 用途：有利因素数量达到此值时，给予较高综合评级
# 默认值：2个
# 业务含义：>= 2个有利因素，配对质量较好
# 评级结果：可能评为A级或A+级（最高级）
# 综合评级逻辑示例：
#   - 高风险>=2 → D/E级（避免）
#   - 中风险>=2且高风险<2 → C级（谨慎）
#   - 有利>=2且高风险=0 → A/A+级（推荐）
#   - 其他情况 → B级（中性）
ALERT_RATING_GREEN_COUNT = int(os.getenv('ALERT_RATING_GREEN_COUNT', '2'))