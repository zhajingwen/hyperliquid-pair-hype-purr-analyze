#!/bin/bash
# =============================================================================
# 数据库时间处理问题修复 - 简化部署脚本（跳过数据库备份）
# =============================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 数据库配置
DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="crypto_data"

echo "============================================================================="
echo "数据库时间处理问题修复 - 简化部署"
echo "============================================================================="
echo ""

# 确认部署
read -p "是否开始部署修复？(y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "部署已取消"
    exit 0
fi

# =============================================================================
# 步骤1: 停止服务 + 备份代码
# =============================================================================
log_info "步骤1: 停止服务 + 备份代码..."

# 停止服务
log_info "停止服务..."
PID=$(ps aux | grep realtime_kline_service_hype | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    kill -15 $PID
    log_info "服务已停止 (PID: $PID)"
    sleep 2
else
    log_warn "服务未运行"
fi

# 备份代码
log_info "备份代码文件..."
BACKUP_TIME=$(date +%Y%m%d_%H%M%S)
cp realtime_kline_service_hype.py realtime_kline_service_hype.py.backup.$BACKUP_TIME
cp utils/timescaledb.py utils/timescaledb.py.backup.$BACKUP_TIME
log_info "✅ 代码备份完成: .backup.$BACKUP_TIME"
echo ""

# =============================================================================
# 步骤2: 运行集成测试
# =============================================================================
log_info "步骤2: 运行集成测试..."

if [ -f "tests/integration_test_timezone.py" ]; then
    python tests/integration_test_timezone.py
    if [ $? -eq 0 ]; then
        log_info "✅ 集成测试通过"
    else
        log_error "❌ 集成测试失败"
        exit 1
    fi
else
    log_warn "集成测试文件不存在，跳过"
fi
echo ""

# =============================================================================
# 步骤3: 重启服务
# =============================================================================
log_info "步骤3: 重启服务..."

# 创建日志目录
mkdir -p logs

# 后台启动服务
LOG_FILE="logs/service_$(date +%Y%m%d).log"
nohup python realtime_kline_service_hype.py > $LOG_FILE 2>&1 &

NEW_PID=$!
log_info "服务已启动 (PID: $NEW_PID)"
log_info "日志文件: $LOG_FILE"

# 等待服务启动
log_info "等待服务启动（10秒）..."
sleep 10

# 检查服务状态
if ps -p $NEW_PID > /dev/null; then
    log_info "✅ 服务运行正常"
else
    log_error "❌ 服务启动失败，请检查日志: $LOG_FILE"
    exit 1
fi
echo ""

# =============================================================================
# 步骤4: 等待数据积累
# =============================================================================
log_info "步骤4: 等待数据积累（3分钟）..."
log_info "提示: 你可以在另一个终端查看日志："
log_info "  tail -f $LOG_FILE"
echo ""

for i in {1..12}; do
    echo -ne "\r进度: $((i*25/3))% [$i/12]"
    sleep 15
done
echo ""
log_info "✅ 等待完成"
echo ""

# =============================================================================
# 步骤5: 快速验证
# =============================================================================
log_info "步骤5: 快速验证..."

log_info "检查最近5分钟的数据..."
python -c "
import psycopg
from datetime import datetime, timezone

try:
    conn = psycopg.connect(
        host='127.0.0.1',
        port=5432,
        dbname='crypto_data',
        user='postgres',
        password='postgres'
    )
    cur = conn.cursor()

    cur.execute('''
        SELECT
            COUNT(*) AS records,
            COUNT(kline_time) AS has_kline_time,
            COUNT(analysis_delay_seconds) AS has_delay,
            COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
            ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay
        FROM analysis_results
        WHERE analysis_time > NOW() - INTERVAL '5 minutes';
    ''')

    result = cur.fetchone()
    records, has_kline, has_delay, neg_delays, avg_delay = result

    print(f'  最近5分钟记录数: {records}')
    print(f'  kline_time 完整性: {has_kline}/{records}')
    print(f'  analysis_delay_seconds 完整性: {has_delay}/{records}')
    print(f'  负延迟数量: {neg_delays}')
    if avg_delay:
        print(f'  平均延迟: {avg_delay}秒')

    # 判断
    if records > 0:
        if has_kline == records and has_delay == records and neg_delays == 0:
            print('\n  ✅ 修复验证成功！')
            exit(0)
        else:
            print('\n  ⚠️  部分字段可能有问题，请检查')
            exit(1)
    else:
        print('\n  ⚠️  暂无新数据，请稍后再验证')
        exit(0)

except Exception as e:
    print(f'  ❌ 数据库连接失败: {e}')
    exit(1)
finally:
    if 'conn' in locals():
        conn.close()
"

VERIFY_RESULT=$?
echo ""

if [ $VERIFY_RESULT -eq 0 ]; then
    log_info "✅ 验证完成"
else
    log_warn "验证结果需要关注，请查看详细信息"
fi
echo ""

# =============================================================================
# 步骤6: 持续监控提示
# =============================================================================
log_info "步骤6: 后续监控建议..."
echo ""
echo "建议在接下来10-15分钟内监控以下指标："
echo ""
echo "1. 查看实时日志："
echo "   tail -f $LOG_FILE"
echo ""
echo "2. 检查服务状态："
echo "   ps aux | grep realtime_kline_service_hype"
echo ""
echo "3. 运行完整验证（5分钟后）："
echo "   python -c \"
import psycopg
conn = psycopg.connect(host='127.0.0.1', port=5432, dbname='crypto_data', user='postgres', password='123456')
cur = conn.cursor()
cur.execute(\\\"\\\"\\\"
SELECT '验证报告' AS name,
       COUNT(*) AS records,
       COUNT(kline_time) AS has_kline_time,
       COUNT(analysis_delay_seconds) AS has_delay,
       COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays,
       ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
       ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds)::NUMERIC, 2) AS p95_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '10 minutes';
\\\"\\\"\\\")
for row in cur.fetchall():
    print(row)
conn.close()
\""
echo ""

# =============================================================================
# 总结
# =============================================================================
echo "============================================================================="
log_info "🎉 部署完成！"
echo "============================================================================="
echo ""
log_info "关键信息："
echo "  - 备份时间: $BACKUP_TIME"
echo "  - 服务PID: $NEW_PID"
echo "  - 日志文件: $LOG_FILE"
echo ""
log_info "如需回滚，执行："
echo "  kill -15 $NEW_PID"
echo "  cp realtime_kline_service_hype.py.backup.$BACKUP_TIME realtime_kline_service_hype.py"
echo "  cp utils/timescaledb.py.backup.$BACKUP_TIME utils/timescaledb.py"
echo "  nohup python realtime_kline_service_hype.py > logs/service.log 2>&1 &"
echo ""
