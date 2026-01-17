#!/usr/bin/env python3
"""
BTC自相关分析结果详细解读
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

def load_results(json_path):
    """加载JSON结果"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_basic_stats(results):
    """分析基础统计"""
    print("=" * 80)
    print("第一部分: 基础统计分析")
    print("=" * 80)

    data_info = results['data_info']
    print(f"\n【数据集信息】")
    print(f"  交易对: {data_info['ticker']}")
    print(f"  时间周期: {data_info['period']} ({data_info['interval']}数据)")
    print(f"  观测数量: {data_info['n_observations']}个")
    print(f"  时间跨度: 约{data_info['n_observations'] / 52:.1f}年")

    acf_data = results['basic_stats']['acf']
    print(f"\n【自相关函数(ACF)分析】")
    print(f"  最大ACF滞后期: lag_{acf_data['max_acf_lag']}")
    print(f"  最大ACF值: {acf_data['acf'][acf_data['max_acf_lag']]:.4f}")
    print(f"  置信区间: ±{acf_data['conf_interval']:.4f}")

    # 显著的ACF滞后期
    acf_values = np.array(acf_data['acf'])
    conf = acf_data['conf_interval']
    significant_lags = []
    for i in range(1, min(21, len(acf_values))):
        if abs(acf_values[i]) > conf:
            significant_lags.append((i, acf_values[i]))

    print(f"\n  显著ACF滞后期(前20期):")
    for lag, value in significant_lags[:10]:
        direction = "正相关" if value > 0 else "负相关"
        print(f"    lag_{lag}: {value:+.4f} ({direction})")

    pacf_data = acf_data['pacf']
    print(f"\n【偏自相关函数(PACF)分析】")
    print(f"  最大PACF滞后期: lag_{acf_data['max_pacf_lag']}")
    print(f"  最大PACF值: {pacf_data[acf_data['max_pacf_lag']]:.4f}")

    # 显著的PACF滞后期
    significant_pacf = []
    for i in range(1, min(21, len(pacf_data))):
        if abs(pacf_data[i]) > conf:
            significant_pacf.append((i, pacf_data[i]))

    print(f"  显著PACF滞后期(前20期):")
    for lag, value in significant_pacf[:10]:
        direction = "正相关" if value > 0 else "负相关"
        print(f"    lag_{lag}: {value:+.4f} ({direction})")

    sign_acf = results['basic_stats']['sign_acf']
    print(f"\n【符号ACF分析(方向持续性)】")
    print(f"  最大符号ACF滞后期: lag_{sign_acf['max_acf_lag']}")
    print(f"  最大符号ACF值: {sign_acf['acf'][sign_acf['max_acf_lag']]:.4f}")

    print(f"\n💡 **基础统计结论**:")
    if len(significant_lags) > 0:
        print(f"  ✓ 发现{len(significant_lags)}个显著的自相关滞后期")
        print(f"  ✓ 最强自相关在lag_{significant_lags[0][0]}")
    else:
        print(f"  ✓ 前20期无显著自相关(接近白噪声)")

    if abs(acf_values[1]) > conf:
        print(f"  ✓ lag_1显著({acf_values[1]:.4f}),存在短期记忆效应")
    else:
        print(f"  ✓ lag_1不显著({acf_values[1]:.4f}),短期记忆较弱")

def analyze_advanced_stats(results):
    """分析高级统计"""
    print("\n" + "=" * 80)
    print("第二部分: 高级统计分析")
    print("=" * 80)

    arch = results['advanced_stats']['arch']
    print(f"\n【ARCH效应检验(波动率聚集)】")
    print(f"  LM统计量: {arch['lm_stat']:.4f}")
    print(f"  LM p值: {arch['lm_pvalue']:.6f}")
    print(f"  F统计量: {arch['f_stat']:.4f}")
    print(f"  F p值: {arch['f_pvalue']:.6f}")
    print(f"  结论: {'存在ARCH效应' if arch['has_arch_effect'] else '不存在ARCH效应'}")

    print(f"\n💡 **ARCH效应含义**:")
    if arch['has_arch_effect']:
        print(f"  ✓ 波动率存在聚集现象")
        print(f"  ✓ 大波动后往往伴随大波动,小波动后往往伴随小波动")
        print(f"  ✓ 建议使用GARCH类模型建模波动率")
        print(f"  ✓ 风险管理需考虑波动率的时变特征")
    else:
        print(f"  ✓ 波动率相对平稳,无明显聚集效应")

def analyze_asymmetric(results):
    """分析不对称性"""
    print("\n" + "=" * 80)
    print("第三部分: 收益率正负不对称性分析")
    print("=" * 80)

    asym = results['asymmetric_analysis']['asymmetric_acf']
    print(f"\n【不对称ACF分析】")
    print(f"  正收益率样本数: {asym['n_pos']}")
    print(f"  负收益率样本数: {asym['n_neg']}")
    print(f"  不对称指数: {asym['asymmetry_index']:.4f}")

    if asym['asymmetry_index'] > 0:
        print(f"  → 负收益率的自相关性更强")
        strength = "强" if abs(asym['asymmetry_index']) > 0.05 else "中等" if abs(asym['asymmetry_index']) > 0.02 else "弱"
        print(f"  → 不对称程度: {strength}")
    else:
        print(f"  → 正收益率的自相关性更强")
        strength = "强" if abs(asym['asymmetry_index']) > 0.05 else "中等" if abs(asym['asymmetry_index']) > 0.02 else "弱"
        print(f"  → 不对称程度: {strength}")

    print(f"\n  正收益率ACF(前5期):")
    for i in range(1, 6):
        if i < len(asym['pos_acf']):
            print(f"    lag_{i}: {asym['pos_acf'][i]:+.4f}")

    print(f"\n  负收益率ACF(前5期):")
    for i in range(1, 6):
        if i < len(asym['neg_acf']):
            print(f"    lag_{i}: {asym['neg_acf'][i]:+.4f}")

    # 分析方向持续性
    persist = results['asymmetric_analysis']['directional_persistence']
    print(f"\n【方向持续性分析】")

    # 计算前5期的平均值
    p_pos_pos = np.mean([persist[str(i)]['p_pos_given_pos'] for i in range(5)])
    p_neg_neg = np.mean([persist[str(i)]['p_neg_given_neg'] for i in range(5)])
    p_pos_neg = np.mean([persist[str(i)]['p_pos_given_neg'] for i in range(5)])
    p_neg_pos = np.mean([persist[str(i)]['p_neg_given_pos'] for i in range(5)])

    print(f"  前5期平均条件概率:")
    print(f"    P(上涨|上涨) = {p_pos_pos:.1%}  {'→ 上涨趋势持续性' if p_pos_pos > 0.5 else '→ 上涨后易反转'}")
    print(f"    P(下跌|下跌) = {p_neg_neg:.1%}  {'→ 下跌趋势持续性' if p_neg_neg > 0.5 else '→ 下跌后易反转'}")
    print(f"    P(上涨|下跌) = {p_pos_neg:.1%}  → 下跌后反转上涨概率")
    print(f"    P(下跌|上涨) = {p_neg_pos:.1%}  → 上涨后反转下跌概率")

    print(f"\n💡 **不对称性交易含义**:")
    if asym['asymmetry_index'] > 0.02:
        print(f"  ⚠️  下跌趋势比上涨趋势更容易延续")
        print(f"  ⚠️  止损策略应更加严格")
        print(f"  ⚠️  下跌过程中反弹难度较大")
    elif asym['asymmetry_index'] < -0.02:
        print(f"  ✓ 上涨趋势比下跌趋势更容易延续")
        print(f"  ✓ 可考虑趋势跟随策略")
    else:
        print(f"  ✓ 正负收益率对称性较好")
        print(f"  ✓ 市场相对平衡")

    if p_neg_neg > p_pos_pos + 0.05:
        print(f"  ⚠️  下跌持续性({p_neg_neg:.1%})显著高于上涨({p_pos_pos:.1%})")
    elif p_pos_pos > p_neg_neg + 0.05:
        print(f"  ✓ 上涨持续性({p_pos_pos:.1%})显著高于下跌({p_neg_neg:.1%})")

def analyze_influence_factors(results):
    """分析影响因素"""
    print("\n" + "=" * 80)
    print("第四部分: 影响因素重要性分析")
    print("=" * 80)

    max_factors = results['importance_analysis']['max_factors']
    print(f"\n【最大影响因素】")
    print(f"  最大影响滞后期: lag_{max_factors['max_influence_lag']}")
    print(f"  综合影响力得分: {max_factors['max_influence_score']:.4f}")

    print(f"\n【Top 10 影响因素排名】")
    ranking = max_factors['influence_ranking']
    for i, (lag, score) in enumerate(ranking.items(), 1):
        print(f"  {i:2d}. lag_{lag:3s}: {score:.4f}")

    # 分析影响力矩阵
    influence_matrix = results['importance_analysis']['influence_matrix']
    print(f"\n【多维度影响力分析】")

    # 获取第一个滞后期作为示例
    first_lag = list(influence_matrix.keys())[0]
    methods = list(influence_matrix[first_lag].keys())

    print(f"  度量方法: {', '.join(methods)}")

    # 分析每个Top 5滞后期的各维度得分
    print(f"\n  Top 5滞后期的详细得分:")
    top_5_lags = list(ranking.keys())[:5]

    for lag in top_5_lags:
        lag_str = str(lag)
        if lag_str in influence_matrix:
            scores = influence_matrix[lag_str]
            print(f"\n  lag_{lag}:")
            for method, value in scores.items():
                print(f"    {method:20s}: {value:.4f}")

    print(f"\n💡 **影响因素解读**:")
    top_lag = max_factors['max_influence_lag']
    top_score = max_factors['max_influence_score']

    print(f"  ✓ lag_{top_lag} 是预测当前收益率的最关键因素")

    if top_lag == 1:
        print(f"  ✓ 前一周的收益率对本周影响最大")
        print(f"  ✓ 市场具有短期记忆效应")
    elif top_lag <= 4:
        print(f"  ✓ 月度周期内的信息最重要")
    elif top_lag <= 13:
        print(f"  ✓ 季度周期的信息最重要")
    else:
        print(f"  ✓ 存在长期记忆效应")

    if top_score > 0.7:
        print(f"  ✓ 影响力得分很高({top_score:.2f}),预测能力强")
    elif top_score > 0.5:
        print(f"  ✓ 影响力得分中等({top_score:.2f}),有一定预测价值")
    else:
        print(f"  ⚠️  影响力得分较低({top_score:.2f}),预测难度大")

    # 分析特征重要性
    if 'feature_importance' in results['importance_analysis']:
        feat_imp = results['importance_analysis']['feature_importance']
        if feat_imp and 'top_lags' in feat_imp:
            print(f"\n【机器学习特征重要性】")
            top_lags = feat_imp['top_lags']
            print(f"  ML模型识别的Top特征:")
            for i, (lag, score) in enumerate(list(top_lags.items())[:5], 1):
                print(f"    {i}. {lag}: {score:.4f}")

def analyze_best_models(results):
    """分析最优模型"""
    print("\n" + "=" * 80)
    print("第五部分: 最优模型分析")
    print("=" * 80)

    best_value = results['best_models']['value']
    best_dir = results['best_models']['direction']

    print(f"\n【最优价值预测模型】")
    print(f"  模型名称: {best_value['model']}")
    print(f"  性能指标:")
    metrics = best_value['metrics']
    print(f"    MAE:  {metrics['mae']:.6f}")
    print(f"    RMSE: {metrics['rmse']:.6f}")
    print(f"    R²:   {metrics['r2']:.6f}")
    print(f"    方向准确率: {metrics['direction_acc']:.2%}")

    print(f"\n  性能评估:")
    if metrics['r2'] > 0.1:
        print(f"    ✓ R²={metrics['r2']:.4f}, 模型有良好的拟合能力")
    elif metrics['r2'] > 0:
        print(f"    ○ R²={metrics['r2']:.4f}, 模型有一定的拟合能力")
    else:
        print(f"    ⚠️  R²={metrics['r2']:.4f}, 模型拟合能力较弱")
        print(f"    → BTC收益率的可预测性较低,主要受随机因素驱动")

    print(f"\n【最优方向预测模型】")
    print(f"  模型名称: {best_dir['model']}")
    print(f"  性能指标:")
    dir_metrics = best_dir['metrics']
    print(f"    Accuracy:  {dir_metrics['accuracy']:.4f}")
    print(f"    Precision: {dir_metrics['precision']:.4f}")
    print(f"    Recall:    {dir_metrics['recall']:.4f}")
    print(f"    F1 Score:  {dir_metrics['f1']:.4f}")

    print(f"\n  性能评估:")
    if dir_metrics['accuracy'] > 0.6:
        print(f"    ✓ 准确率{dir_metrics['accuracy']:.1%}, 方向预测有价值")
    elif dir_metrics['accuracy'] > 0.55:
        print(f"    ○ 准确率{dir_metrics['accuracy']:.1%}, 略优于随机")
    else:
        print(f"    ⚠️  准确率{dir_metrics['accuracy']:.1%}, 接近随机猜测")

    if dir_metrics['recall'] == 1.0:
        print(f"    ⚠️  Recall=1.0, 模型倾向于全部预测为上涨")
        print(f"    → 可能存在样本不平衡问题")

    print(f"\n💡 **模型选择建议**:")
    print(f"  价值预测: 使用{best_value['model']}")
    print(f"    → 适用于: 量化回测、风险评估")
    print(f"    → RMSE={metrics['rmse']:.4f}, 预测误差约为{metrics['rmse']*100:.2f}%")

    print(f"\n  方向预测: 使用{best_dir['model']}")
    print(f"    → 适用于: 趋势判断、交易信号")
    print(f"    → 准确率={dir_metrics['accuracy']:.1%}")

    if metrics['r2'] < 0:
        print(f"\n  ⚠️  重要提示:")
        print(f"    → BTC周收益率的可预测性非常有限")
        print(f"    → 价格主要受突发事件和情绪驱动")
        print(f"    → 建议结合基本面分析和风险管理")
        print(f"    → 避免过度依赖历史数据预测")

def generate_trading_insights(results):
    """生成交易洞察"""
    print("\n" + "=" * 80)
    print("第六部分: 交易策略洞察")
    print("=" * 80)

    # 综合分析
    asym_idx = results['asymmetric_analysis']['asymmetric_acf']['asymmetry_index']
    has_arch = results['advanced_stats']['arch']['has_arch_effect']
    top_lag = results['importance_analysis']['max_factors']['max_influence_lag']
    best_acc = results['best_models']['direction']['metrics']['accuracy']

    print(f"\n【市场特征总结】")
    print(f"  1. 记忆效应: lag_{top_lag}影响最大")
    if top_lag == 1:
        print(f"     → 强短期记忆,动量效应显著")
    elif top_lag <= 4:
        print(f"     → 月度周期重要")
    else:
        print(f"     → 存在长期周期效应")

    print(f"\n  2. 不对称性: {asym_idx:.4f}")
    if abs(asym_idx) > 0.02:
        if asym_idx > 0:
            print(f"     → 下跌更易延续,需严格止损")
        else:
            print(f"     → 上涨更易延续,可持有优质资产")
    else:
        print(f"     → 涨跌对称,市场相对平衡")

    print(f"\n  3. 波动率: {'聚集效应显著' if has_arch else '相对平稳'}")
    if has_arch:
        print(f"     → 大波动后注意风险管理")
        print(f"     → 可使用GARCH模型预测波动率")

    print(f"\n  4. 可预测性: {best_acc:.1%}")
    if best_acc > 0.6:
        print(f"     → 较高,可构建量化策略")
    elif best_acc > 0.55:
        print(f"     → 中等,需谨慎使用")
    else:
        print(f"     → 较低,更适合长期投资")

    print(f"\n【策略建议】")

    # 趋势跟随策略
    print(f"\n  🎯 趋势跟随策略:")
    if top_lag <= 2:
        print(f"     ✓ 可行性: 高")
        print(f"     ✓ 利用短期动量效应")
        print(f"     ✓ 持仓周期: 1-2周")
    else:
        print(f"     ○ 可行性: 中等")
        print(f"     ○ 需结合其他指标")

    # 均值回归策略
    print(f"\n  🔄 均值回归策略:")
    if abs(asym_idx) < 0.02:
        print(f"     ✓ 可行性: 中等")
        print(f"     ✓ 市场涨跌对称,存在回归机会")
    else:
        print(f"     ⚠️  可行性: 低")
        print(f"     ⚠️  存在不对称性,回归难以把握")

    # 风险管理
    print(f"\n  🛡️  风险管理建议:")
    if has_arch:
        print(f"     ⚠️  使用动态止损")
        print(f"     ⚠️  波动率高时减小仓位")
        print(f"     ⚠️  考虑波动率目标策略")

    if asym_idx > 0.02:
        print(f"     ⚠️  下跌时快速止损")
        print(f"     ⚠️  上涨时可适当持有")
    elif asym_idx < -0.02:
        print(f"     ✓ 上涨趋势更稳定")
        print(f"     ✓ 可适当放宽止损")

    print(f"\n  ⏰ 持仓周期建议:")
    if top_lag == 1:
        print(f"     → 短期交易(1-2周)")
    elif top_lag <= 4:
        print(f"     → 中短期(1个月)")
    else:
        print(f"     → 中长期(3个月以上)")

def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("BTC周收益率自相关分析 - 详细统计解读")
    print("=" * 80)

    # 加载结果
    json_path = "btc_analysis_results/summary.json"
    results = load_results(json_path)

    # 各部分分析
    analyze_basic_stats(results)
    analyze_advanced_stats(results)
    analyze_asymmetric(results)
    analyze_influence_factors(results)
    analyze_best_models(results)
    generate_trading_insights(results)

    print("\n" + "=" * 80)
    print("分析报告完成")
    print("=" * 80)
    print(f"\n详细数据文件:")
    print(f"  - summary.json: 完整数据")
    print(f"  - report.md: Markdown报告")
    print(f"  - *.csv: 各类分析数据")
    print(f"  - figures/*.png: 可视化图表")

if __name__ == "__main__":
    main()
