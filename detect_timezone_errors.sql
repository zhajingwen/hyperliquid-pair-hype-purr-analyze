-- =====================================================
-- 检测历史数据时区错误
-- 用于部署前识别8小时时区偏移问题
-- =====================================================

-- 检测1: 负延迟（8小时偏移的标志）
SELECT
    '检测1: 负延迟（8小时偏移标志）' AS check_name,
    symbol,
    kline_time,
    analysis_time,
    analysis_delay_seconds,
    EXTRACT(EPOCH FROM (analysis_time - kline_time)) AS calculated_delay,
    CASE
        WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN '⚠️ 8小时偏移'
        WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) > 3600 THEN '⚠️ 异常延迟'
        WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < 0 THEN '⚠️ 负延迟'
        ELSE '✓ 正常'
    END AS status
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 day'
ORDER BY analysis_time DESC
LIMIT 50;

-- 检测2: 统计时区偏移数据
SELECT
    '检测2: 时区偏移统计' AS check_name,
    COUNT(*) AS total_records,
    COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN 1 END) AS offset_8h_records,
    COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < 0 THEN 1 END) AS negative_delay_records,
    COUNT(CASE WHEN kline_time IS NULL THEN 1 END) AS null_kline_time,
    COUNT(CASE WHEN analysis_delay_seconds IS NULL THEN 1 END) AS null_delay_seconds,
    ROUND(
        100.0 * COUNT(CASE WHEN EXTRACT(EPOCH FROM (analysis_time - kline_time)) < -28700 THEN 1 END) / NULLIF(COUNT(*), 0),
        2
    ) AS offset_percentage
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '7 days';

-- 检测3: 延迟分布（用于验证数据质量）
SELECT
    '检测3: 延迟分布' AS check_name,
    MIN(EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS min_delay,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS p25_delay,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS median_delay,
    AVG(EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS avg_delay,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS p75_delay,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS p95_delay,
    MAX(EXTRACT(EPOCH FROM (analysis_time - kline_time))) AS max_delay
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '7 days'
  AND kline_time IS NOT NULL;

-- 检测4: 字段完整性
SELECT
    '检测4: 字段完整性' AS check_name,
    COUNT(*) AS total_records,
    COUNT(kline_time) AS has_kline_time,
    COUNT(analysis_delay_seconds) AS has_delay_seconds,
    ROUND(100.0 * COUNT(kline_time) / NULLIF(COUNT(*), 0), 2) AS kline_time_coverage,
    ROUND(100.0 * COUNT(analysis_delay_seconds) / NULLIF(COUNT(*), 0), 2) AS delay_seconds_coverage
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '7 days';

-- 检测5: 时区一致性（与klines表对比）
SELECT
    '检测5: 时区一致性' AS check_name,
    ar.symbol,
    ar.kline_time AS analysis_kline_time,
    k.time AS klines_time,
    EXTRACT(EPOCH FROM (ar.kline_time - k.time)) AS time_diff_seconds,
    CASE
        WHEN ABS(EXTRACT(EPOCH FROM (ar.kline_time - k.time))) < 1 THEN '✓ 一致'
        WHEN ABS(EXTRACT(EPOCH FROM (ar.kline_time - k.time))) BETWEEN 28700 AND 28900 THEN '⚠️ 8小时偏移'
        ELSE '⚠️ 不一致'
    END AS consistency_status
FROM analysis_results ar
LEFT JOIN klines k ON ar.symbol = k.symbol
    AND ar.kline_time BETWEEN k.time - INTERVAL '5 minutes' AND k.time + INTERVAL '5 minutes'
    AND k.timeframe = '5m'
WHERE ar.analysis_time > NOW() - INTERVAL '1 day'
  AND ar.kline_time IS NOT NULL
ORDER BY ar.analysis_time DESC
LIMIT 30;
