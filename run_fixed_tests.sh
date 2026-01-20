#!/bin/bash

# 模块3修复后的测试运行脚本

echo "🔧 运行修复后的测试..."
echo "=================================="

# 运行失败的测试
echo "📊 测试 analysis_core 和 realtime_service..."
python -m pytest tests/unit/test_analysis_core.py tests/unit/test_realtime_service.py -v --tb=short -x

echo ""
echo "✅ 测试完成！"
