#!/usr/bin/env python3
"""
验证优化效果 - 使用真实数据

对比优化前后协整检验的改进
"""

import ccxt
import time
import logging
import numpy as np
import pandas as pd
from retry import retry
from utils.config import lark_bot_id
from multi_coins4 import DelayCorrelationAnalyzer, setup_logging

# 初始化日志
logger = setup_logging(level=logging.INFO)

def verify_single_pair(exchange, base_symbol, coin, timeframe='4h', limit=360):
    """验证单个币种对的优化效果"""
    logger.info(f"\n{'='*80}")
    logger.info(f"验证币种对: {coin} vs {base_symbol}")
    logger.info(f"{'='*80}")
    
    try:
        # 获取数据
        base_ohlcv = exchange.fetch_ohlcv(base_symbol, timeframe=timeframe, limit=limit)
        alt_ohlcv = exchange.fetch_ohlcv(coin, timeframe=timeframe, limit=limit)
        
        base_df = pd.DataFrame(base_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        alt_df = pd.DataFrame(alt_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        base_prices = base_df['close']
        alt_prices = alt_df['close']
        
        # Old方法（全量数据）
        logger.info(f"\n--- Old方法（全量{len(base_prices)}期数据） ---")
        ols_params = DelayCorrelationAnalyzer._calculate_cointegration_params(
            base_prices, alt_prices, coin=coin, base_symbol=base_symbol
        )
        
        if ols_params:
            logger.info(f"  α = {ols_params['alpha']:.4f} (p值={ols_params.get('alpha_pvalue', 'N/A'):.4f})")
            logger.info(f"  β = {ols_params['beta']:.4f} (p值={ols_params.get('beta_pvalue', 'N/A'):.4f})")
            logger.info(f"  R² = {ols_params.get('rsquared', 'N/A'):.4f}")
            logger.info(f"  模型类型: {ols_params.get('model_type', 'N/A')}")
            logger.info(f"  使用α: {ols_params.get('use_alpha', 'N/A')}")
            logger.info(f"  ADF p值 = {ols_params['adf_pvalue']:.4f}")
            
            if ols_params['adf_pvalue'] < 0.05:
                logger.info(f"  ✅ 通过协整检验 (p < 0.05)")
            else:
                logger.info(f"  ❌ 未通过协整检验 (p >= 0.05)")
        
        # New方法（100期窗口）
        logger.info(f"\n--- New方法（100期窗口） ---")
        cointegration_result = DelayCorrelationAnalyzer.price_diff_spread_ols_window(
            base_prices, alt_prices, beta_window=100, zscore_window=30
        )
        
        if cointegration_result:
            logger.info(f"  α = {cointegration_result['alpha']:.4f} (p值={cointegration_result.get('alpha_pvalue', 'N/A'):.4f})")
            logger.info(f"  β = {cointegration_result['beta']:.4f} (p值={cointegration_result.get('beta_pvalue', 'N/A'):.4f})")
            logger.info(f"  R² = {cointegration_result.get('rsquared', 'N/A'):.4f}")
            logger.info(f"  模型类型: {cointegration_result.get('model_type', 'N/A')}")
            logger.info(f"  使用α: {cointegration_result.get('use_alpha', 'N/A')}")
            logger.info(f"  ADF p值 = {cointegration_result['adf_pvalue']:.4f}")
            
            if cointegration_result['adf_pvalue'] < 0.05:
                logger.info(f"  ✅ 通过协整检验 (p < 0.05)")
            else:
                logger.info(f"  ❌ 未通过协整检验 (p >= 0.05)")
        
        # 对比
        logger.info(f"\n--- 对比分析 ---")
        if ols_params and cointegration_result:
            # 模型选择对比
            old_model = ols_params.get('model_type', 'N/A')
            new_model = cointegration_result.get('model_type', 'N/A')
            
            if old_model == new_model:
                logger.info(f"  模型选择: 两者一致 ({old_model})")
            else:
                logger.info(f"  模型选择: Old={old_model}, New={new_model}")
            
            # ADF p值对比
            old_p = ols_params['adf_pvalue']
            new_p = cointegration_result['adf_pvalue']
            
            if abs(old_p - new_p) < 0.01:
                logger.info(f"  ADF p值: 两者接近 (Old={old_p:.4f}, New={new_p:.4f})")
            else:
                logger.info(f"  ADF p值: 存在差异 (Old={old_p:.4f}, New={new_p:.4f})")
        
        return True
        
    except Exception as e:
        logger.error(f"验证失败: {type(e).__name__}: {str(e)}")
        return False


def main():
    """主函数"""
    logger.info("="*80)
    logger.info("协整检验优化效果验证")
    logger.info("="*80)
    
    # 初始化交易所
    exchange = ccxt.hyperliquid()
    
    # 基准币种
    base_symbol = 'BTC/USDC:USDC'
    
    # 测试币种对（从日志中选择之前HEALTHY的）
    test_pairs = [
        'NEAR/USDC:USDC',
        'ETH/USDC:USDC',
        'NOT/USDC:USDC',
        'OP/USDC:USDC',
    ]
    
    results = {}
    for coin in test_pairs:
        success = verify_single_pair(exchange, base_symbol, coin)
        results[coin] = success
        time.sleep(1)  # 避免请求过快
    
    # 总结
    logger.info(f"\n{'='*80}")
    logger.info("验证总结")
    logger.info(f"{'='*80}")
    
    successful = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"成功验证: {successful}/{total} 个币种对")
    
    for coin, success in results.items():
        status = "✅" if success else "❌"
        logger.info(f"  {status} {coin}")
    
    logger.info(f"\n优化验证完成！")


if __name__ == '__main__':
    main()
