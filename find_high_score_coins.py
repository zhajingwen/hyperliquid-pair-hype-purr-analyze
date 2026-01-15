#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从日志文件中找出短期窗口(100期)和长期窗口(200期)综合得分都大于10的代币
"""

import re
from pathlib import Path

def parse_log_file(log_path):
    """解析日志文件，找出符合条件的代币"""
    results = []
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 查找币种名称
        coin_match = re.search(r'协整健康监控 \| 币种: ([^\s]+)', line)
        if coin_match:
            coin = coin_match.group(1)
            long_score = None
            short_score = None
            
            # 向前查找长期窗口和短期窗口的得分
            j = i
            while j < len(lines) and j < i + 20:  # 在接下来的20行内查找
                current_line = lines[j]
                
                # 查找长期窗口200期的综合得分
                if '【长期窗口 200期】' in current_line:
                    # 下一行应该包含综合得分
                    if j + 1 < len(lines):
                        score_match = re.search(r'综合得分:\s*([\d.]+)', lines[j + 1])
                        if score_match:
                            long_score = float(score_match.group(1))
                
                # 查找短期窗口100期的综合得分
                if '【短期窗口 100期】' in current_line:
                    # 下一行应该包含综合得分
                    if j + 1 < len(lines):
                        score_match = re.search(r'综合得分:\s*([\d.]+)', lines[j + 1])
                        if score_match:
                            short_score = float(score_match.group(1))
                
                j += 1
            
            # 如果两个得分都大于10，记录这个币种
            if long_score is not None and short_score is not None:
                if long_score > 10 and short_score > 10:
                    results.append({
                        'coin': coin,
                        'long_score': long_score,
                        'short_score': short_score
                    })
        
        i += 1
    
    return results

def main():
    log_path = Path(__file__).parent / 'multi_coins5.log'
    
    print(f"正在解析日志文件: {log_path}")
    print("=" * 60)
    
    results = parse_log_file(log_path)
    
    if results:
        print(f"\n找到 {len(results)} 个符合条件的代币：\n")
        print(f"{'代币':<30} {'长期窗口(200期)':<20} {'短期窗口(100期)':<20}")
        print("-" * 70)
        
        # 按长期得分降序排序
        results.sort(key=lambda x: x['long_score'], reverse=True)
        
        for r in results:
            print(f"{r['coin']:<30} {r['long_score']:<20.2f} {r['short_score']:<20.2f}")
        
        print("\n" + "=" * 60)
        print(f"总计: {len(results)} 个代币")
    else:
        print("\n未找到符合条件的代币（短期窗口和长期窗口综合得分都大于10）")

if __name__ == '__main__':
    main()
