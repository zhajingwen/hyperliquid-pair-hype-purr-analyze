#!/bin/bash
# 数据库死锁实时监控脚本 - HYPE版本
# Author: Claude Code
# Date: 2026-01-29

LOG_FILE="purr_hype.log"
MONITOR_MINUTES=30

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=========================================="
echo "🔍 数据库死锁实时监控 (HYPE版本)"
echo "=========================================="
echo -e "${BLUE}监控时长: ${MONITOR_MINUTES} 分钟${NC}"
echo -e "${BLUE}日志文件: ${LOG_FILE}${NC}"
echo -e "${BLUE}监控币种: HYPE/USDC:USDC, PURR/USDC:USDC${NC}"
echo ""
echo "按 Ctrl+C 停止监控"
echo "=========================================="
echo ""

# 检查日志文件是否存在
if [ ! -f "$LOG_FILE" ]; then
    echo -e "${YELLOW}⚠️  日志文件 ${LOG_FILE} 不存在${NC}"
    echo "请确认服务是否已启动："
    echo "  python realtime_kline_service_hype.py &"
    exit 1
fi

# 创建临时文件记录监控数据
TEMP_FILE=$(mktemp)
trap "rm -f $TEMP_FILE" EXIT

# 记录开始时间
START_TIME=$(date +%s)
echo -e "${GREEN}开始时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""

# 初始化计数器
total_deadlocks=0
successful_retries=0
failed_retries=0
kline_deadlocks=0
analysis_deadlocks=0

# 监控函数
monitor_deadlocks() {
    local check_interval=10  # 每10秒检查一次
    local end_time=$((START_TIME + MONITOR_MINUTES * 60))

    while [ $(date +%s) -lt $end_time ]; do
        # 统计死锁事件
        kline_deadlocks=$(grep "K线写入死锁" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
        analysis_deadlocks=$(grep "分析结果写入死锁" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
        total_deadlocks=$((kline_deadlocks + analysis_deadlocks))

        # 统计成功重试和失败重试
        successful_retries=$(grep "死锁.*重试" "$LOG_FILE" 2>/dev/null | grep -v "重试耗尽" | wc -l | tr -d ' ')
        failed_retries=$(grep "重试耗尽" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

        # 显示统计信息
        clear
        echo "=========================================="
        echo "🔍 数据库死锁实时监控 (HYPE版本)"
        echo "=========================================="
        echo -e "${BLUE}运行时长: $(($(date +%s) - START_TIME)) 秒 / $((MONITOR_MINUTES * 60)) 秒${NC}"
        echo ""
        echo "📊 死锁统计:"
        echo "----------------------------------------"
        if [ $total_deadlocks -gt 0 ]; then
            echo -e "总死锁事件: ${YELLOW}${total_deadlocks}${NC}"
            echo -e "  - K线写入: ${kline_deadlocks}"
            echo -e "  - 分析结果写入: ${analysis_deadlocks}"
            echo ""
            echo -e "成功重试: ${GREEN}${successful_retries}${NC}"
            echo -e "重试耗尽: ${RED}${failed_retries}${NC}"

            local success_rate=$((successful_retries * 100 / total_deadlocks))
            echo -e "重试成功率: ${GREEN}${success_rate}%${NC}"

            echo ""
            echo "📝 最近死锁日志:"
            echo "----------------------------------------"
            tail -5 "$LOG_FILE" 2>/dev/null | grep -i "死锁"
        else
            echo -e "${GREEN}✅ 无死锁事件${NC}"
            echo ""
            echo "📝 最近批量写入日志:"
            echo "----------------------------------------"
            tail -3 "$LOG_FILE" 2>/dev/null | grep "批量写入" || echo "（等待批量写入...）"
        fi

        echo ""
        echo "=========================================="
        echo "按 Ctrl+C 停止监控"
        echo "=========================================="

        sleep $check_interval
    done
}

# 监控死锁
monitor_deadlocks

# 显示最终统计
clear
echo "=========================================="
echo "📊 监控完成 - 最终统计 (HYPE版本)"
echo "=========================================="
echo -e "${BLUE}监控时长: ${MONITOR_MINUTES} 分钟${NC}"
echo ""
echo "死锁统计:"
echo "----------------------------------------"
echo -e "总死锁事件: ${YELLOW}${total_deadlocks}${NC}"
echo -e "  - K线写入: ${kline_deadlocks}"
echo -e "  - 分析结果写入: ${analysis_deadlocks}"
echo ""
echo -e "成功重试: ${GREEN}${successful_retries}${NC}"
echo -e "重试耗尽: ${RED}${failed_retries}${NC}"

if [ $total_deadlocks -gt 0 ]; then
    success_rate=$((successful_retries * 100 / total_deadlocks))
    echo -e "重试成功率: ${GREEN}${success_rate}%${NC}"

    # 每小时死锁频率
    hourly_rate=$((total_deadlocks * 60 / MONITOR_MINUTES))
    echo -e "预计每小时死锁: ${YELLOW}${hourly_rate}${NC} 次"

    # 评估修复效果
    echo ""
    echo "修复效果评估:"
    echo "----------------------------------------"
    if [ $success_rate -ge 95 ] && [ $hourly_rate -lt 5 ]; then
        echo -e "${GREEN}✅ 优秀！重试成功率 >95%，死锁频率 <5次/小时${NC}"
    elif [ $success_rate -ge 90 ] && [ $hourly_rate -lt 10 ]; then
        echo -e "${GREEN}✅ 良好！重试成功率 >90%，死锁频率 <10次/小时${NC}"
    elif [ $success_rate -ge 80 ]; then
        echo -e "${YELLOW}⚠️  一般，重试成功率 >80%，但仍有优化空间${NC}"
    else
        echo -e "${RED}❌ 需要进一步优化！重试成功率 <80%${NC}"
        echo "建议:"
        echo "1. 检查数据库负载"
        echo "2. 启用数据库死锁日志"
        echo "3. 考虑实施阶段2优化（方案2/3）"
    fi
else
    echo -e "${GREEN}✅ 完美！监控期间无死锁事件${NC}"
fi

echo ""
echo "=========================================="
echo "详细日志查看："
echo "  tail -f ${LOG_FILE} | grep -i 'deadlock'"
echo "=========================================="
