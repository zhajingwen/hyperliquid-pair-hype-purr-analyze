-- =====================================================
-- 数据库字段兼容性验证脚本
-- 用途: 验证 analysis_results 表数据写入正确性
-- 版本: 1.0
-- =====================================================

-- 1. 验证表结构
\echo '========================================='
\echo '📋 验证 analysis_results 表结构'
\echo '========================================='

\d analysis_results

-- 2. 查看最近的分析记录
\echo ''
\echo '========================================='
\echo '📊 最近1小时的分析记录'
\echo '========================================='

SELECT
    analysis_time,
    symbol,
    base_symbol,

    -- 相关系数（多周期验证应为NULL）
    corr_5m_7d,
    corr_1h_30d,
    corr_4h_60d,

    -- 多周期Z-score（应有值）
    zscore_5m,
    zscore_1h,
    zscore_4h,

    -- 协整检验（应有值）
    cointegration_passed,
    adf_pvalue,

    -- 信号判断（应有值）
    is_anomaly,
    trading_direction,
    signal_strength,

    created_at
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 hour'
ORDER BY analysis_time DESC
LIMIT 10;

-- 3. 验证字段完整性统计
\echo ''
\echo '========================================='
\echo '🔍 字段完整性统计（最近24小时）'
\echo '========================================='

SELECT
    -- 相关系数字段（预期为NULL）
    COUNT(*) FILTER (WHERE corr_5m_7d IS NOT NULL) AS corr_5m_count,
    COUNT(*) FILTER (WHERE corr_1h_30d IS NOT NULL) AS corr_1h_count,
    COUNT(*) FILTER (WHERE corr_4h_60d IS NOT NULL) AS corr_4h_count,

    -- Z-score字段（预期有值）
    COUNT(*) FILTER (WHERE zscore_5m IS NOT NULL) AS zscore_5m_count,
    COUNT(*) FILTER (WHERE zscore_1h IS NOT NULL) AS zscore_1h_count,
    COUNT(*) FILTER (WHERE zscore_4h IS NOT NULL) AS zscore_4h_count,

    -- 协整检验字段
    COUNT(*) FILTER (WHERE cointegration_passed IS NOT NULL) AS coint_passed_count,
    COUNT(*) FILTER (WHERE adf_pvalue IS NOT NULL) AS adf_pvalue_count,

    -- 信号字段（预期有值）
    COUNT(*) FILTER (WHERE is_anomaly IS NOT NULL) AS is_anomaly_count,
    COUNT(*) FILTER (WHERE trading_direction IS NOT NULL) AS direction_count,
    COUNT(*) FILTER (WHERE signal_strength IS NOT NULL) AS strength_count,

    -- 总记录数
    COUNT(*) AS total_records
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '24 hours';

-- 4. 验证数据类型
\echo ''
\echo '========================================='
\echo '🧪 数据类型验证（最近记录）'
\echo '========================================='

SELECT
    symbol,

    -- Z-score范围验证（应在合理范围内）
    zscore_5m,
    zscore_1h,
    zscore_4h,

    -- 布尔值验证
    cointegration_passed,
    is_anomaly,

    -- 字符串值验证
    trading_direction,
    signal_strength,

    -- 时间戳验证
    analysis_time,
    created_at
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '1 hour'
ORDER BY analysis_time DESC
LIMIT 5;

-- 5. 异常数据检测
\echo ''
\echo '========================================='
\echo '⚠️  异常数据检测'
\echo '========================================='

-- 检测Z-score异常值（超出合理范围）
SELECT
    'Z-score超出范围(-10, 10)' AS issue_type,
    COUNT(*) AS issue_count
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '24 hours'
  AND (
      ABS(zscore_5m) > 10 OR
      ABS(zscore_1h) > 10 OR
      ABS(zscore_4h) > 10
  )

UNION ALL

-- 检测缺失必需字段
SELECT
    '缺失必需字段（is_anomaly）' AS issue_type,
    COUNT(*) AS issue_count
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '24 hours'
  AND is_anomaly IS NULL

UNION ALL

-- 检测trading_direction取值异常
SELECT
    'trading_direction取值异常' AS issue_type,
    COUNT(*) AS issue_count
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '24 hours'
  AND trading_direction NOT IN ('long', 'short', 'none')
  AND trading_direction IS NOT NULL;

-- 6. 信号统计
\echo ''
\echo '========================================='
\echo '📈 信号统计（最近24小时）'
\echo '========================================='

SELECT
    trading_direction,
    signal_strength,
    COUNT(*) AS signal_count,
    AVG(zscore_5m) AS avg_zscore_5m,
    AVG(zscore_1h) AS avg_zscore_1h,
    AVG(zscore_4h) AS avg_zscore_4h,
    COUNT(*) FILTER (WHERE cointegration_passed = TRUE) AS coint_pass_count
FROM analysis_results
WHERE analysis_time > NOW() - INTERVAL '24 hours'
  AND is_anomaly = TRUE
GROUP BY trading_direction, signal_strength
ORDER BY signal_count DESC;

\echo ''
\echo '========================================='
\echo '✅ 验证完成！'
\echo '========================================='
\echo ''
\echo '预期结果：'
\echo '1. corr_5m_7d, corr_1h_30d, corr_4h_60d 应全为 NULL'
\echo '2. zscore_5m, zscore_1h, zscore_4h 应有值'
\echo '3. cointegration_passed 应为布尔值（基于协整通过数 >= 2）'
\echo '4. adf_pvalue 应为 NULL（多周期验证无单一p值）'
\echo '5. is_anomaly 应全为 TRUE（通过多周期验证才写入）'
\echo '6. trading_direction 应为 long/short'
\echo '7. signal_strength 应为 strong'
\echo ''
