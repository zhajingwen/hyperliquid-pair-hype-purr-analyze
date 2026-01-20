#!/bin/bash
# =====================================================
# 测试数据库设置脚本
# 用途: 为测试创建独立的测试数据库
# =====================================================

set -e  # 遇到错误立即退出

echo "========================================="
echo "🔧 配置测试数据库环境"
echo "========================================="

# 配置参数
CONTAINER_NAME="crypto_timescaledb"
DB_USER="postgres"
TEST_DB_NAME="crypto_data_test"
INIT_SQL_PATH="$(dirname "$0")/../init_timescaledb.sql"

# 检查Docker容器是否运行
echo ""
echo "1️⃣ 检查TimescaleDB容器..."
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ 错误: TimescaleDB容器未运行"
    echo "请先启动容器: docker-compose up -d"
    exit 1
fi
echo "✅ TimescaleDB容器正在运行"

# 检查是否可以连接
echo ""
echo "2️⃣ 测试数据库连接..."
if ! docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" > /dev/null 2>&1; then
    echo "❌ 错误: 无法连接到数据库"
    exit 1
fi
echo "✅ 数据库连接正常"

# 删除旧的测试数据库（如果存在）
echo ""
echo "3️⃣ 清理旧的测试数据库..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $TEST_DB_NAME;" 2>/dev/null || true
echo "✅ 旧数据库已清理"

# 创建新的测试数据库
echo ""
echo "4️⃣ 创建测试数据库: $TEST_DB_NAME"
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $TEST_DB_NAME;"
echo "✅ 测试数据库已创建"

# 初始化数据库结构
echo ""
echo "5️⃣ 初始化数据库结构..."
if [ -f "$INIT_SQL_PATH" ]; then
    docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB_NAME" < "$INIT_SQL_PATH"
    echo "✅ 数据库结构已初始化"
else
    echo "⚠️  警告: 找不到初始化脚本 $INIT_SQL_PATH"
    echo "请手动初始化数据库结构"
fi

# 验证测试数据库
echo ""
echo "6️⃣ 验证测试数据库..."
TABLE_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$TABLE_COUNT" -ge 3 ]; then
    echo "✅ 测试数据库验证成功 (发现 $TABLE_COUNT 张表)"
else
    echo "⚠️  警告: 表数量异常 (发现 $TABLE_COUNT 张表，期望至少3张)"
fi

# 显示测试数据库信息
echo ""
echo "========================================="
echo "✅ 测试数据库配置完成！"
echo "========================================="
echo ""
echo "测试数据库信息:"
echo "  - 数据库名: $TEST_DB_NAME"
echo "  - 主机: 127.0.0.1"
echo "  - 端口: 5432"
echo "  - 用户: $DB_USER"
echo ""
echo "下一步:"
echo "  1. 运行测试: pytest tests/ -v"
echo "  2. 运行单元测试: pytest tests/unit/ -v -m unit"
echo "  3. 运行集成测试: pytest tests/integration/ -v -m integration"
echo "  4. 查看覆盖率: pytest tests/ -v --cov=utils.timescaledb --cov-report=html"
echo ""
