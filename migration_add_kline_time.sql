-- ==========================================
-- 迁移脚本：添加 kline_time 和 analysis_delay_seconds 字段
-- 执行时间：预计 < 1秒（如果表数据量 < 100万行）
-- ==========================================

BEGIN;

-- 1. 添加新字段（允许 NULL，避免锁表时间过长）
ALTER TABLE analysis_results
ADD COLUMN IF NOT EXISTS kline_time TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS analysis_delay_seconds FLOAT;

-- 2. 为现有数据设置默认值
-- 策略：kline_time = analysis_time（假设延迟为0）
UPDATE analysis_results
SET kline_time = analysis_time,
    analysis_delay_seconds = 0
WHERE kline_time IS NULL;

-- 3. 添加注释
COMMENT ON COLUMN analysis_results.kline_time IS 'K线原始时间（触发分析的K线的闭合时间）';
COMMENT ON COLUMN analysis_results.analysis_delay_seconds IS '分析延迟（秒）= analysis_time - kline_time';

COMMIT;

-- 4. 验证迁移结果
SELECT
    COUNT(*) as total_records,
    COUNT(kline_time) as kline_time_filled,
    COUNT(analysis_delay_seconds) as delay_filled,
    AVG(analysis_delay_seconds) as avg_delay
FROM analysis_results;
