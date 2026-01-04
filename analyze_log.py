#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析日志文件，提取所有被划归到"常规数据"的代币及其占比
"""

import re
from collections import defaultdict

def analyze_log(log_file_path):
    """分析日志文件"""
    normal_coins = []  # 常规数据币种列表
    total_coins = None  # 总币种数
    
    # 正则表达式
    normal_data_pattern = r'常规数据\s*\|\s*币种:\s*([^/]+)/USDC:USDC'
    total_coins_pattern = r'发现\s+(\d+)\s+个\s+USDC\s+永续合约交易对'
    
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 提取总币种数（只取第一个匹配的，应该是多币种分析的开始）
            if total_coins is None:
                match = re.search(total_coins_pattern, line)
                if match:
                    total_coins = int(match.group(1))
                    print(f"发现总币种数: {total_coins}")
            
            # 提取常规数据的币种
            match = re.search(normal_data_pattern, line)
            if match:
                coin = match.group(1)
                normal_coins.append(coin)
    
    # 去重并统计
    unique_normal_coins = list(set(normal_coins))
    unique_normal_coins.sort()
    
    # 统计每个币种出现的次数
    coin_counts = defaultdict(int)
    for coin in normal_coins:
        coin_counts[coin] += 1
    
    # 计算占比
    if total_coins:
        percentage = (len(unique_normal_coins) / total_coins) * 100
    else:
        percentage = None
        print("警告: 未找到总币种数信息")
    
    return {
        'total_coins': total_coins,
        'normal_coins': unique_normal_coins,
        'normal_coins_count': len(unique_normal_coins),
        'normal_coins_total_occurrences': len(normal_coins),
        'coin_counts': dict(coin_counts),
        'percentage': percentage
    }

def main():
    log_file = '/Users/test/Downloads/hyperliquid-pair-hype-purr-analyze/hyperliquid.log'
    
    print("=" * 80)
    print("日志分析：常规数据代币统计")
    print("=" * 80)
    print()
    
    result = analyze_log(log_file)
    
    print(f"总币种数: {result['total_coins']}")
    print(f"常规数据币种数（去重后）: {result['normal_coins_count']}")
    print(f"常规数据币种总出现次数: {result['normal_coins_total_occurrences']}")
    if result['percentage'] is not None:
        print(f"占比: {result['percentage']:.2f}%")
    print()
    
    print("=" * 80)
    print("常规数据代币列表（按字母顺序）:")
    print("=" * 80)
    for i, coin in enumerate(result['normal_coins'], 1):
        count = result['coin_counts'][coin]
        print(f"{i:3d}. {coin:20s} (出现 {count} 次)")
    
    print()
    print("=" * 80)
    print("统计摘要:")
    print("=" * 80)
    print(f"总币种数: {result['total_coins']}")
    print(f"常规数据币种数: {result['normal_coins_count']}")
    if result['percentage'] is not None:
        print(f"占比: {result['percentage']:.2f}%")
    print(f"其他币种数: {result['total_coins'] - result['normal_coins_count'] if result['total_coins'] else '未知'}")

if __name__ == '__main__':
    main()

