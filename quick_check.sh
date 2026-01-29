#!/bin/bash
# 快速检查验证脚本修复效果

set -e

echo "=========================================="
echo "验证脚本修复快速检查"
echo "=========================================="
echo ""

# 检查Python版本
echo "1️⃣  检查Python环境..."
python3 --version || { echo "❌ Python3未安装"; exit 1; }
echo "✅ Python环境正常"
echo ""

# 检查依赖
echo "2️⃣  检查依赖库..."
python3 -c "import psycopg" 2>/dev/null && echo "✅ psycopg已安装" || echo "⚠️  psycopg未安装（可能使用psycopg2）"
python3 -c "import psycopg2" 2>/dev/null && echo "✅ psycopg2已安装" || echo "⚠️  psycopg2未安装（可能使用psycopg）"
echo ""

# 检查数据库连接（通过Python脚本）
echo "3️⃣  检查数据库连接..."
python3 -c "
from utils.timescaledb import TimescaleDBClient
try:
    client = TimescaleDBClient()
    if client.health_check():
        print('✅ 数据库连接正常')
    else:
        print('❌ 数据库连接失败')
        exit(1)
    client.close()
except Exception as e:
    print(f'❌ 数据库连接错误: {e}')
    exit(1)
" || { echo ""; echo "请检查数据库配置"; exit 1; }
echo ""

# 检查修改后的代码语法
echo "4️⃣  检查代码语法..."
python3 -m py_compile validate_data_consistency.py && echo "✅ 代码语法正确" || { echo "❌ 代码语法错误"; exit 1; }
echo ""

# 询问是否运行测试
echo "=========================================="
echo "环境检查完成！"
echo "=========================================="
echo ""
echo "接下来可以："
echo "  1. 运行对比测试: python3 test_validation_fix.py"
echo "  2. 运行验证脚本: python3 validate_data_consistency.py --hours 1"
echo ""

read -p "是否现在运行对比测试？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "=========================================="
    echo "运行对比测试..."
    echo "=========================================="
    echo ""
    python3 test_validation_fix.py

    echo ""
    echo "=========================================="
    echo "测试完成！"
    echo "=========================================="
    echo ""

    read -p "是否运行修复后的验证脚本？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "=========================================="
        echo "运行验证脚本（最近1小时数据）..."
        echo "=========================================="
        echo ""
        python3 validate_data_consistency.py --hours 1 --format text

        echo ""
        echo "=========================================="
        echo "✅ 所有测试完成！"
        echo "=========================================="
    fi
else
    echo ""
    echo "已跳过测试。您可以稍后手动运行："
    echo "  python3 test_validation_fix.py"
    echo "  python3 validate_data_consistency.py --hours 1"
fi

echo ""
echo "📚 查看详细文档："
echo "  - 修复说明: VALIDATION_FIX_SUMMARY.md"
echo "  - 变更记录: CHANGES.md"
echo ""
