#!/usr/bin/env python
"""
数据库迁移执行脚本
读取 migration_add_kline_time.sql 并执行
"""
import psycopg
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('TIMESCALEDB_HOST', '127.0.0.1'),
    'port': int(os.getenv('TIMESCALEDB_PORT', 5432)),
    'database': os.getenv('TIMESCALEDB_NAME', 'crypto_data'),
    'user': os.getenv('TIMESCALEDB_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}

def run_migration():
    """执行数据库迁移"""
    print("=" * 60)
    print("开始执行数据库迁移：添加 kline_time 和 analysis_delay_seconds")
    print("=" * 60)

    # 读取迁移脚本
    migration_file = 'migration_add_kline_time.sql'
    print(f"\n读取迁移脚本: {migration_file}")

    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # 移除 psql 命令（如果有）
    sql_statements = []
    for line in sql_content.split('\n'):
        # 跳过注释和空行
        line = line.strip()
        if not line or line.startswith('--'):
            continue
        sql_statements.append(line)

    sql_script = '\n'.join(sql_statements)

    # 连接数据库
    print(f"\n连接数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    try:
        # 构建连接字符串
        conninfo = f"host={DB_CONFIG['host']} port={DB_CONFIG['port']} " \
                   f"dbname={DB_CONFIG['database']} user={DB_CONFIG['user']} " \
                   f"password={DB_CONFIG['password']}"

        conn = psycopg.connect(conninfo, autocommit=True)
        cur = conn.cursor()

        print("\n执行迁移脚本...")
        cur.execute(sql_script)

        # 验证字段是否添加成功
        print("\n验证字段是否添加...")
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'analysis_results'
            AND column_name IN ('kline_time', 'analysis_delay_seconds')
            ORDER BY column_name;
        """)

        columns = cur.fetchall()
        if len(columns) == 2:
            print("✓ 字段添加成功:")
            for col_name, col_type in columns:
                print(f"  - {col_name}: {col_type}")
        else:
            print("✗ 字段添加失败")
            return False

        # 检查现有数据
        print("\n检查现有数据默认值...")
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(kline_time) as kline_time_filled,
                COUNT(analysis_delay_seconds) as delay_filled,
                AVG(analysis_delay_seconds) as avg_delay
            FROM analysis_results;
        """)

        result = cur.fetchone()
        total, kline_filled, delay_filled, avg_delay = result

        print(f"  总记录数: {total}")
        print(f"  kline_time 已填充: {kline_filled}")
        print(f"  analysis_delay_seconds 已填充: {delay_filled}")
        print(f"  平均延迟: {avg_delay:.2f} 秒" if avg_delay else "  平均延迟: N/A")

        if total > 0:
            if kline_filled == total and delay_filled == total:
                print("✓ 所有现有记录已成功填充默认值")
            else:
                print("⚠ 部分记录未填充默认值")
        else:
            print("ℹ 表中暂无数据")

        cur.close()
        conn.close()

        print("\n" + "=" * 60)
        print("✓ 数据库迁移完成")
        print("=" * 60)
        return True

    except psycopg.Error as e:
        print(f"\n✗ 数据库错误: {e}")
        return False
    except Exception as e:
        print(f"\n✗ 执行失败: {e}")
        return False

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
