#!/bin/bash

# 最终修复验证脚本

echo "🔍 验证模块3最终测试修复..."
echo "=================================="
echo ""

echo "📌 步骤1: 运行之前失败的测试..."
echo ""

# 运行之前失败的特定测试
python -m pytest tests/unit/test_realtime_service.py::TestAnalysisWorker::test_dedup_strategy_5m -v

if [ $? -eq 0 ]; then
    echo "✅ test_dedup_strategy_5m 通过!"
else
    echo "❌ test_dedup_strategy_5m 仍然失败"
    exit 1
fi

echo ""
echo "📌 步骤2: 验证pytest不会误收集test_cointegration..."
echo ""

# 尝试收集所有测试,检查是否还有错误
python -m pytest tests/unit/test_analysis_core.py --collect-only 2>&1 | grep -i "error"

if [ $? -ne 0 ]; then
    echo "✅ 没有pytest收集错误!"
else
    echo "⚠️  仍有收集错误"
fi

echo ""
echo "📌 步骤3: 运行完整单元测试套件..."
echo ""

python -m pytest tests/unit/ -v --tb=short

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 所有单元测试通过!"
else
    echo ""
    echo "⚠️  部分测试失败,请查看上面的输出"
    exit 1
fi

echo ""
echo "=================================="
echo "✅ 最终修复验证完成!"
echo ""
echo "修复总结:"
echo "  - test_dedup_strategy_5m: Mock路径修复"
echo "  - test_cointegration: 函数重命名为check_cointegration"
echo "  - 所有单元测试通过率: 100%"
echo ""
echo "🚀 项目测试状态: 生产就绪!"
