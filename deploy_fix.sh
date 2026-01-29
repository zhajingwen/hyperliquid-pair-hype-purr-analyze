#!/bin/bash
# =============================================================================
# 数据库时间处理问题修复 - 快速部署脚本
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

# =============================================================================
# 步骤1: 备份
# =============================================================================
backup() {
    log_info "步骤1: 开始备份..."

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
    log_info "代码备份完成: .backup.$BACKUP_TIME"

    # 备份数据库
    log_info "备份数据库（最近7天）..."
    pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
        -t analysis_results --data-only \
        --where="analysis_time > NOW() - INTERVAL '7 days'" \
        > backup_analysis_$BACKUP_TIME.sql
    log_info "数据库备份完成: backup_analysis_$BACKUP_TIME.sql"

    log_info "✅ 备份完成"
}

# =============================================================================
# 步骤2: 检测历史错误数据
# =============================================================================
detect_errors() {
    log_info "步骤2: 检测历史错误数据..."

    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f detect_timezone_errors.sql

    log_info "✅ 错误检测完成"
}

# =============================================================================
# 步骤3: 修正历史数据（可选）
# =============================================================================
fix_historical_data() {
    log_warn "步骤3: 修正历史数据（可选）..."

    read -p "是否修正最近7天的8小时偏移数据？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "开始修正历史数据..."

        psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME <<EOF
UPDATE analysis_results
SET
    kline_time = kline_time - INTERVAL '8 hours',
    analysis_delay_seconds = EXTRACT(EPOCH FROM (analysis_time - (kline_time - INTERVAL '8 hours')))
WHERE kline_time IS NOT NULL
  AND EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700
  AND analysis_time > NOW() - INTERVAL '7 days';
EOF

        log_info "✅ 历史数据修正完成"
    else
        log_info "跳过历史数据修正"
    fi
}

# =============================================================================
# 步骤4: 运行集成测试
# =============================================================================
run_tests() {
    log_info "步骤4: 运行集成测试..."

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
}

# =============================================================================
# 步骤5: 重启服务
# =============================================================================
restart_service() {
    log_info "步骤5: 重启服务..."

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
}

# =============================================================================
# 步骤6: 验证修复
# =============================================================================
verify_fix() {
    log_info "步骤6: 验证修复..."

    # 等待数据积累
    log_info "等待数据积累（3分钟）..."
    sleep 180

    # 运行验证脚本
    log_info "运行验证脚本..."
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f tests/verify_timezone_fix.sql

    log_info "✅ 验证完成"
}

# =============================================================================
# 步骤7: 持续监控
# =============================================================================
monitor() {
    log_info "步骤7: 持续监控（5分钟）..."

    for i in {1..5}; do
        log_info "监控检查 $i/5..."

        psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME <<EOF
SELECT
    '监控报告' AS report_name,
    COUNT(*) AS records_last_1min,
    COUNT(DISTINCT symbol) AS symbols,
    ROUND(AVG(analysis_delay_seconds)::NUMERIC, 2) AS avg_delay,
    COUNT(CASE WHEN kline_time IS NULL THEN 1 END) AS missing_kline_time,
    COUNT(CASE WHEN analysis_delay_seconds < 0 THEN 1 END) AS negative_delays
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 minute';
EOF

        if [ $i -lt 5 ]; then
            sleep 60
        fi
    done

    log_info "✅ 监控完成"
}

# =============================================================================
# 主函数
# =============================================================================
main() {
    echo "============================================================================="
    echo "数据库时间处理问题修复 - 快速部署"
    echo "============================================================================="
    echo ""

    # 确认部署
    read -p "是否开始部署修复？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "部署已取消"
        exit 0
    fi

    # 执行部署步骤
    backup
    echo ""

    detect_errors
    echo ""

    fix_historical_data
    echo ""

    run_tests
    echo ""

    restart_service
    echo ""

    verify_fix
    echo ""

    monitor
    echo ""

    echo "============================================================================="
    log_info "🎉 部署完成！"
    echo "============================================================================="
    echo ""
    log_info "后续步骤："
    echo "  1. 查看实时日志: tail -f logs/service_\$(date +%Y%m%d).log"
    echo "  2. 检查服务状态: ps aux | grep realtime_kline_service_hype"
    echo "  3. 手动验证: psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f tests/verify_timezone_fix.sql"
    echo ""
}

# 运行主函数
main
