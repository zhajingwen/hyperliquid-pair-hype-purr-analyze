-- =====================================================
-- 时区错误数据清理脚本
-- 用途: 删除K线数据中时区处理错误的记录
-- 日期: 2026-01-29
-- =====================================================

\echo '========================================='
\echo '时区错误数据清理'
\echo '========================================='
\echo ''

-- 步骤1: 统计错误数据
\echo '步骤1: 统计错误数据...'
SELECT 
    COUNT(*) as total_bad_records,
    COUNT(DISTINCT symbol) as affected_symbols,
    MIN(time) as earliest_bad_time,
    MAX(time) as latest_bad_time
FROM klines 
WHERE time > created_at + INTERVAL '1 hour';

\echo ''
\echo '========================================='

-- 步骤2: 查看部分错误数据样本
\echo '步骤2: 查看错误数据样本（前10条）...'
SELECT 
    symbol,
    timeframe,
    time,
    created_at,
    EXTRACT(EPOCH FROM (time - created_at)) / 3600 as diff_hours
FROM klines 
WHERE time > created_at + INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;

\echo ''
\echo '========================================='

-- 步骤3: 删除错误数据
\echo '步骤3: 执行删除操作...'
\echo '警告: 此操作不可逆！'
\echo ''

BEGIN;

DELETE FROM klines 
WHERE time > created_at + INTERVAL '1 hour';

\echo ''
\echo '删除完成，正在提交事务...'

COMMIT;

\echo ''
\echo '========================================='

-- 步骤4: 验证清理结果
\echo '步骤4: 验证清理结果...'
SELECT 
    COUNT(*) as remaining_bad_records,
    CASE 
        WHEN COUNT(*) = 0 THEN '✅ 清理成功'
        ELSE '⚠️ 仍有错误数据'
    END as status
FROM klines 
WHERE time > created_at + INTERVAL '1 hour';

\echo ''
\echo '========================================='
\echo '清理完成！'
\echo '========================================='
\echo ''
\echo '建议后续操作:'
\echo '1. 重启实时数据采集服务'
\echo '2. 运行数据一致性验证: uv run validate_data_consistency.py'
\echo '3. 如需回填数据: 使用 kline_data_filler.py'
\echo ''
