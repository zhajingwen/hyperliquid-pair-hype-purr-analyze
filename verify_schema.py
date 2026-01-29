#!/usr/bin/env python
"""
Schema 验证脚本
验证 analysis_results 表结构和索引
"""
import sys
sys.path.insert(0, '.venv/lib/python3.14/site-packages')

import psycopg

# 数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 5432,
    'database': 'crypto_data',
    'user': 'postgres',
    'password': 'postgres'
}

def verify_schema():
    """验证数据库 schema"""
    print("=" * 60)
    print("验证数据库 Schema")
    print("=" * 60)

    conninfo = f"host={DB_CONFIG['host']} port={DB_CONFIG['port']} " \
               f"dbname={DB_CONFIG['database']} user={DB_CONFIG['user']} " \
               f"password={DB_CONFIG['password']}"

    try:
        with psycopg.connect(conninfo) as conn:
            with conn.cursor() as cur:
                # 1. 验证字段定义
                print("\n1. 验证字段定义:")
                print("-" * 60)
                cur.execute("""
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_name = 'analysis_results'
                    AND column_name IN ('kline_time', 'analysis_delay_seconds', 'analysis_time', 'symbol')
                    ORDER BY ordinal_position;
                """)

                columns = cur.fetchall()
                for col_name, data_type, is_nullable, default_val in columns:
                    nullable = "NULL" if is_nullable == 'YES' else "NOT NULL"
                    default_str = f"DEFAULT {default_val}" if default_val else ""
                    print(f"  {col_name:30s} {data_type:20s} {nullable:10s} {default_str}")

                # 2. 验证索引
                print("\n2. 验证索引:")
                print("-" * 60)
                cur.execute("""
                    SELECT
                        i.indexname,
                        i.indexdef
                    FROM pg_indexes i
                    WHERE i.tablename = 'analysis_results'
                    AND (i.indexname LIKE '%kline_time%' OR i.indexname LIKE '%delay%')
                    ORDER BY i.indexname;
                """)

                indexes = cur.fetchall()
                if indexes:
                    for idx_name, idx_def in indexes:
                        print(f"  ✓ {idx_name}")
                        print(f"    {idx_def}")
                else:
                    print("  ℹ 新索引尚未创建（可选，init_timescaledb.sql 中定义）")

                # 3. 验证字段注释
                print("\n3. 验证字段注释:")
                print("-" * 60)
                cur.execute("""
                    SELECT
                        a.attname AS column_name,
                        d.description
                    FROM pg_class c
                    JOIN pg_attribute a ON a.attrelid = c.oid
                    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = a.attnum
                    WHERE c.relname = 'analysis_results'
                    AND a.attname IN ('kline_time', 'analysis_delay_seconds')
                    AND a.attnum > 0
                    ORDER BY a.attname;
                """)

                comments = cur.fetchall()
                for col_name, description in comments:
                    desc = description if description else "（无注释）"
                    print(f"  {col_name}: {desc}")

                # 4. 数据统计
                print("\n4. 数据统计:")
                print("-" * 60)
                cur.execute("""
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(kline_time) as kline_time_filled,
                        COUNT(analysis_delay_seconds) as delay_filled,
                        MIN(analysis_time) as earliest_analysis,
                        MAX(analysis_time) as latest_analysis
                    FROM analysis_results;
                """)

                result = cur.fetchone()
                total, kline_filled, delay_filled, earliest, latest = result

                print(f"  总记录数: {total:,}")
                print(f"  kline_time 填充率: {kline_filled}/{total} ({100*kline_filled/total if total > 0 else 0:.1f}%)")
                print(f"  delay 填充率: {delay_filled}/{total} ({100*delay_filled/total if total > 0 else 0:.1f}%)")
                print(f"  最早分析: {earliest}")
                print(f"  最新分析: {latest}")

        print("\n" + "=" * 60)
        print("✓ Schema 验证完成")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = verify_schema()
    exit(0 if success else 1)
