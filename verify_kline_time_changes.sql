-- ==========================================
-- 验证脚本：kline_time 和 analysis_delay_seconds 字段验证
-- 用途：在服务运行后验证新字段的数据正确性
-- ==========================================

\echo '=========================================='
\echo '验证1: 新字段非空检查'
\echo '=========================================='

SELECT
    COUNT(*) as total_records,
    COUNT(kline_time) as kline_time_count,
    COUNT(analysis_delay_seconds) as delay_count,
    COUNT(*) - COUNT(kline_time) as kline_time_null,
    COUNT(*) - COUNT(analysis_delay_seconds) as delay_null
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '15 minutes';

\echo ''
\echo '预期: kline_time_count = total_records, delay_count = total_records'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证2: 延迟计算正确性检查'
\echo '=========================================='

SELECT
    symbol,
    kline_time,
    analysis_time,
    analysis_delay_seconds,
    EXTRACT(EPOCH FROM (analysis_time - kline_time)) as calculated_delay,
    ABS(analysis_delay_seconds - EXTRACT(EPOCH FROM (analysis_time - kline_time))) as diff
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '15 minutes'
ORDER BY analysis_time DESC
LIMIT 10;

\echo ''
\echo '预期: diff < 0.001 (延迟计算误差小于1毫秒)'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证3: kline_time 与 klines 表对齐检查'
\echo '=========================================='

SELECT
    a.symbol,
    a.kline_time as analysis_kline_time,
    k.time as klines_table_time,
    a.analysis_delay_seconds,
    CASE
        WHEN a.kline_time = k.time THEN '✓ 对齐'
        ELSE '✗ 不对齐'
    END as alignment_status
FROM analysis_results a
JOIN klines k ON
    a.symbol = k.symbol
    AND k.timeframe = '5m'
    AND k.time = a.kline_time
WHERE a.analysis_time > NOW() - INTERVAL '15 minutes'
ORDER BY a.analysis_time DESC
LIMIT 10;

\echo ''
\echo '预期: 所有记录都能成功 JOIN，alignment_status = ✓ 对齐'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证4: 延迟分布统计'
\echo '=========================================='

SELECT
    MIN(analysis_delay_seconds) as min_delay,
    AVG(analysis_delay_seconds) as avg_delay,
    MAX(analysis_delay_seconds) as max_delay,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p50_delay,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p95_delay,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY analysis_delay_seconds) as p99_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '15 minutes';

\echo ''
\echo '预期: avg_delay 在 5-10秒范围，p95 < 15秒'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证5: 去重逻辑验证（按分钟级）'
\echo '=========================================='

SELECT
    DATE_TRUNC('minute', analysis_time) as minute,
    symbol,
    COUNT(*) as count
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 hour'
GROUP BY minute, symbol
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 10;

\echo ''
\echo '预期: 无重复记录（结果为空）'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证6: 高延迟分析识别'
\echo '=========================================='

SELECT
    symbol,
    kline_time,
    analysis_time,
    analysis_delay_seconds
FROM analysis_results
WHERE analysis_delay_seconds > 10
  AND analysis_time > NOW() - INTERVAL '1 day'
ORDER BY analysis_delay_seconds DESC
LIMIT 20;

\echo ''
\echo '预期: 列出所有延迟超过10秒的分析记录'
\echo ''

-- ==========================================
\echo '=========================================='
\echo '验证7: 延迟趋势分析（按小时）'
\echo '=========================================='

SELECT
    DATE_TRUNC('hour', analysis_time) as hour,
    COUNT(*) as analysis_count,
    AVG(analysis_delay_seconds) as avg_delay,
    MAX(analysis_delay_seconds) as max_delay,
    MIN(analysis_delay_seconds) as min_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 day'
GROUP BY hour
ORDER BY hour DESC;

\echo ''
\echo '预期: 显示每小时的延迟趋势统计'
\echo ''
\echo '=========================================='
\echo '✓ 验证脚本执行完成'
\echo '=========================================='
