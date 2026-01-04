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
    skipped_coins = []  # 跳过的币种列表（数据不存在）
    anomaly_coins = []  # 异常币种列表（仅从multi_coins.py）
    checked_coins = []  # 所有被检查的币种（仅从multi_coins.py）
    total_coins = None  # 总币种数
    
    # 正则表达式
    normal_data_pattern = r'常规数据\s*\|\s*币种:\s*([^/]+)/USDC:USDC'
    skipped_pattern = r'币种数据不存在，跳过后续所有组合\s*\|\s*币种:\s*([^/]+)/USDC:USDC'
    anomaly_pattern = r'发现异常币种\s*\|\s*交易所:\s*hyperliquid\s*\|\s*币种:\s*([^/]+)/USDC:USDC'
    checked_pattern = r'检查币种:\s*([^/]+)/USDC:USDC'
    total_coins_pattern = r'发现\s+(\d+)\s+个\s+USDC\s+永续合约交易对'
    
    # 用于过滤multi_coins.py的异常币种（不是purr5.py的）
    in_multi_coins_analysis = False
    
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 检测是否进入multi_coins分析
            if 'multi_coins.py' in line and '启动分析器' in line:
                in_multi_coins_analysis = True
            elif 'multi_coins.py' in line and '分析完成' in line:
                in_multi_coins_analysis = False
            
            # 提取总币种数（只取第一个匹配的，应该是多币种分析的开始）
            if total_coins is None:
                match = re.search(total_coins_pattern, line)
                if match:
                    total_coins = int(match.group(1))
                    print(f"发现总币种数: {total_coins}")
            
            # 提取所有被检查的币种（仅从multi_coins.py）
            match = re.search(checked_pattern, line)
            if match and in_multi_coins_analysis and 'multi_coins.py' in line:
                coin = match.group(1)
                checked_coins.append(coin)
            
            # 提取常规数据的币种
            match = re.search(normal_data_pattern, line)
            if match:
                coin = match.group(1)
                normal_coins.append(coin)
            
            # 提取跳过的币种
            match = re.search(skipped_pattern, line)
            if match:
                coin = match.group(1)
                skipped_coins.append(coin)
            
            # 提取异常币种（仅从multi_coins.py）
            match = re.search(anomaly_pattern, line)
            if match and in_multi_coins_analysis and 'multi_coins.py' in line:
                coin = match.group(1)
                anomaly_coins.append(coin)
    
    # 去重并统计
    unique_normal_coins = sorted(list(set(normal_coins)))
    unique_skipped_coins = sorted(list(set(skipped_coins)))
    unique_anomaly_coins = sorted(list(set(anomaly_coins)))
    unique_checked_coins = sorted(list(set(checked_coins)))
    
    # 找出其他情况的币种（被检查了但没有被归类到常规、跳过或异常）
    all_accounted_coins = set(unique_normal_coins) | set(unique_skipped_coins) | set(unique_anomaly_coins)
    other_coins = sorted(list(set(unique_checked_coins) - all_accounted_coins))
    
    # 统计每个币种出现的次数
    normal_coin_counts = defaultdict(int)
    for coin in normal_coins:
        normal_coin_counts[coin] += 1
    
    # 计算占比
    if total_coins:
        normal_percentage = (len(unique_normal_coins) / total_coins) * 100
        skipped_percentage = (len(unique_skipped_coins) / total_coins) * 100
        anomaly_percentage = (len(unique_anomaly_coins) / total_coins) * 100
        other_percentage = (len(other_coins) / total_coins) * 100 if other_coins else 0
    else:
        normal_percentage = None
        skipped_percentage = None
        anomaly_percentage = None
        other_percentage = None
        print("警告: 未找到总币种数信息")
    
    return {
        'total_coins': total_coins,
        'normal_coins': unique_normal_coins,
        'normal_coins_count': len(unique_normal_coins),
        'normal_coins_total_occurrences': len(normal_coins),
        'normal_coin_counts': dict(normal_coin_counts),
        'normal_percentage': normal_percentage,
        'skipped_coins': unique_skipped_coins,
        'skipped_coins_count': len(unique_skipped_coins),
        'skipped_percentage': skipped_percentage,
        'anomaly_coins': unique_anomaly_coins,
        'anomaly_coins_count': len(unique_anomaly_coins),
        'anomaly_percentage': anomaly_percentage,
        'other_coins': other_coins,
        'other_coins_count': len(other_coins),
        'other_percentage': other_percentage,
        'checked_coins': unique_checked_coins,
    }

def main():
    log_file = '/Users/test/Downloads/hyperliquid-pair-hype-purr-analyze/hyperliquid.log'
    
    print("=" * 80)
    print("日志分析：常规数据代币统计")
    print("=" * 80)
    print()
    
    result = analyze_log(log_file)
    
    print(f"总币种数: {result['total_coins']}")
    print()
    
    print("=" * 80)
    print("分类统计:")
    print("=" * 80)
    print(f"常规数据币种数（去重后）: {result['normal_coins_count']}")
    if result['normal_percentage'] is not None:
        print(f"  占比: {result['normal_percentage']:.2f}%")
    print(f"  总出现次数: {result['normal_coins_total_occurrences']}")
    print()
    
    print(f"跳过币种数（数据不存在）: {result['skipped_coins_count']}")
    if result['skipped_percentage'] is not None:
        print(f"  占比: {result['skipped_percentage']:.2f}%")
    print()
    
    print(f"异常币种数（multi_coins.py）: {result['anomaly_coins_count']}")
    if result['anomaly_percentage'] is not None:
        print(f"  占比: {result['anomaly_percentage']:.2f}%")
    print()
    
    # 显示其他情况
    print(f"其他情况币种数: {result['other_coins_count']}")
    if result['other_percentage'] is not None:
        print(f"  占比: {result['other_percentage']:.2f}%")
    print()
    
    print("=" * 80)
    print("跳过币种列表（数据不存在）:")
    print("=" * 80)
    if result['skipped_coins']:
        for i, coin in enumerate(result['skipped_coins'], 1):
            print(f"{i:3d}. {coin}")
    else:
        print("无")
    print()
    
    print("=" * 80)
    print("异常币种列表（multi_coins.py）:")
    print("=" * 80)
    if result['anomaly_coins']:
        for i, coin in enumerate(result['anomaly_coins'], 1):
            print(f"{i:3d}. {coin}")
    else:
        print("无")
    print()
    
    print("=" * 80)
    print("其他情况币种列表（已检查但未明确归类）:")
    print("=" * 80)
    if result['other_coins']:
        for i, coin in enumerate(result['other_coins'], 1):
            print(f"{i:3d}. {coin}")
        print()
        print("这些币种可能的情况：")
        print("  1. 分析过程中出错但未明确标记")
        print("  2. 数据不足但未触发跳过逻辑")
        print("  3. 其他未预期的处理路径")
    else:
        print("无")
    print()
    
    print("=" * 80)
    print("常规数据代币列表（按字母顺序，前20个）:")
    print("=" * 80)
    for i, coin in enumerate(result['normal_coins'][:20], 1):
        count = result['normal_coin_counts'][coin]
        print(f"{i:3d}. {coin:20s} (出现 {count} 次)")
    if len(result['normal_coins']) > 20:
        print(f"... 还有 {len(result['normal_coins']) - 20} 个币种")
    print()
    
    print("=" * 80)
    print("统计摘要:")
    print("=" * 80)
    print(f"总币种数: {result['total_coins']}")
    print(f"  - 常规数据: {result['normal_coins_count']} ({result['normal_percentage']:.2f}%)" if result['normal_percentage'] else f"  - 常规数据: {result['normal_coins_count']}")
    print(f"  - 跳过（数据不存在）: {result['skipped_coins_count']} ({result['skipped_percentage']:.2f}%)" if result['skipped_percentage'] else f"  - 跳过（数据不存在）: {result['skipped_coins_count']}")
    print(f"  - 异常: {result['anomaly_coins_count']} ({result['anomaly_percentage']:.2f}%)" if result['anomaly_percentage'] else f"  - 异常: {result['anomaly_coins_count']}")
    if result['other_coins_count'] > 0:
        print(f"  - 其他: {result['other_coins_count']} ({result['other_percentage']:.2f}%)" if result['other_percentage'] else f"  - 其他: {result['other_coins_count']}")

if __name__ == '__main__':
    main()

