#!/bin/bash
# 模块3测试运行脚本
# 
# 使用方法:
#   ./run_module3_tests.sh [unit|integration|performance|all|coverage]

set -e

echo "========================================"
echo "模块3: 实时分析引擎测试套件"
echo "========================================"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 测试类型参数
TEST_TYPE=${1:-all}

case $TEST_TYPE in
  unit)
    echo -e "${YELLOW}运行单元测试...${NC}"
    pytest tests/unit/test_analysis_core.py \
           tests/unit/test_health_monitor.py \
           tests/unit/test_reconnection_manager.py \
           tests/unit/test_ws_manager.py \
           tests/unit/test_realtime_service.py \
           -v --tb=short
    ;;
    
  integration)
    echo -e "${YELLOW}运行集成测试（需要数据库）...${NC}"
    pytest tests/integration/test_realtime_dataflow.py \
           tests/integration/test_analysis_workflow.py \
           tests/integration/test_alert_integration.py \
           -v --tb=short
    ;;
    
  performance)
    echo -e "${YELLOW}运行性能测试...${NC}"
    pytest tests/performance/test_realtime_performance.py \
           -v --tb=short
    ;;
    
  coverage)
    echo -e "${YELLOW}运行测试并生成覆盖率报告...${NC}"
    pytest tests/unit/ tests/integration/ \
           -v \
           --cov=utils.analysis_core \
           --cov=utils.enhanced_ws_manager \
           --cov=realtime_kline_service \
           --cov-report=html:htmlcov_module3 \
           --cov-report=term-missing \
           --cov-report=xml:coverage_module3.xml
    
    echo -e "${GREEN}✅ 覆盖率报告已生成${NC}"
    echo -e "HTML报告: htmlcov_module3/index.html"
    echo -e "XML报告: coverage_module3.xml"
    ;;
    
  all)
    echo -e "${YELLOW}运行所有测试...${NC}"
    
    echo -e "\n${YELLOW}[1/3] 单元测试${NC}"
    pytest tests/unit/test_analysis_core.py \
           tests/unit/test_health_monitor.py \
           tests/unit/test_reconnection_manager.py \
           tests/unit/test_ws_manager.py \
           tests/unit/test_realtime_service.py \
           -v --tb=short
    
    echo -e "\n${YELLOW}[2/3] 集成测试${NC}"
    pytest tests/integration/test_realtime_dataflow.py \
           tests/integration/test_analysis_workflow.py \
           tests/integration/test_alert_integration.py \
           -v --tb=short
    
    echo -e "\n${YELLOW}[3/3] 性能测试${NC}"
    pytest tests/performance/test_realtime_performance.py \
           -v --tb=short
    
    echo -e "\n${GREEN}✅ 所有测试完成${NC}"
    ;;
    
  *)
    echo -e "${RED}未知的测试类型: $TEST_TYPE${NC}"
    echo "使用方法: $0 [unit|integration|performance|all|coverage]"
    exit 1
    ;;
esac

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}测试运行完成！${NC}"
echo -e "${GREEN}========================================${NC}"
