#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从日志文件中找出短期窗口（100期）和长期窗口（200期）稳定性得分都大于6，且短期改善的代币
"""

import re
from pathlib import Path

def parse_log_file(log_path):
    """解析日志文件，提取稳定性得分和趋势判断信息"""
    results = []
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 查找币种信息
        coin_match = re.search(r'协整健康监控 \| 币种: ([^|]+)', line)
        if coin_match:
            coin = coin_match.group(1).strip()
            long_term_stability = None
            short_term_stability = None
            is_improving = False
            
            # 继续读取后续行，查找长期和短期窗口的稳定性得分
            j = i + 1
            while j < len(lines) and j < i + 25:  # 最多查找25行
                current_line = lines[j]
                
                # 查找长期窗口 200期
                if '【长期窗口 200期】' in current_line:
                    # 继续查找稳定性得分
                    k = j + 1
                    while k < len(lines) and k < j + 10:
                        stability_line = lines[k]
                        stability_match = re.search(r'稳定性: ([\d.]+)', stability_line)
                        if stability_match:
                            long_term_stability = float(stability_match.group(1))
                            break
                        k += 1
                
                # 查找短期窗口 100期
                if '【短期窗口 100期】' in current_line:
                    # 继续查找稳定性得分
                    k = j + 1
                    while k < len(lines) and k < j + 10:
                        stability_line = lines[k]
                        stability_match = re.search(r'稳定性: ([\d.]+)', stability_line)
                        if stability_match:
                            short_term_stability = float(stability_match.group(1))
                            break
                        k += 1
                
                # 查找趋势判断
                if '趋势判断' in current_line and '短期改善' in current_line:
                    is_improving = True
                
                j += 1
            
            # 如果找到了两个稳定性得分，保存结果
            if long_term_stability is not None and short_term_stability is not None:
                results.append({
                    'coin': coin,
                    'long_term_stability': long_term_stability,
                    'short_term_stability': short_term_stability,
                    'is_improving': is_improving
                })
        
        i += 1
    
    return results

def filter_coins(results, stability_threshold=6):
    """筛选出两个窗口稳定性得分都大于阈值且短期改善的代币"""
    filtered = []
    for result in results:
        if (result['long_term_stability'] > stability_threshold and 
            result['short_term_stability'] > stability_threshold and
            result['is_improving']):
            filtered.append(result)
    return filtered

def main():
    log_path = Path(__file__).parent / 'multi_coins5.log'
    
    print(f"正在解析日志文件: {log_path}")
    print("=" * 80)
    
    # 解析日志
    all_results = parse_log_file(log_path)
    print(f"共找到 {len(all_results)} 个代币的稳定性得分记录")
    
    # 筛选符合条件的代币
    filtered_results = filter_coins(all_results, stability_threshold=6)
    
    print("\n" + "=" * 80)
    print(f"符合条件的代币（短期窗口100期和长期窗口200期稳定性得分都 > 6，且短期改善）：")
    print("=" * 80)
    
    if filtered_results:
        # 按稳定性得分总和排序
        filtered_results.sort(key=lambda x: x['long_term_stability'] + x['short_term_stability'], reverse=True)
        
        print(f"\n共找到 {len(filtered_results)} 个符合条件的代币：\n")
        print(f"{'代币':<30} {'长期窗口(200期)':<20} {'短期窗口(100期)':<20} {'总分':<10}")
        print("-" * 80)
        
        for result in filtered_results:
            total_score = result['long_term_stability'] + result['short_term_stability']
            print(f"{result['coin']:<30} {result['long_term_stability']:<20.1f} {result['short_term_stability']:<20.1f} {total_score:<10.1f}")
    else:
        print("\n未找到符合条件的代币")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
