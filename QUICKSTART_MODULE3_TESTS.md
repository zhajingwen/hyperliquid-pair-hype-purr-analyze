# 模块3测试快速开始指南

## 🚀 5分钟快速开始

### 1. 安装依赖（1分钟）

```bash
pip install pytest pytest-cov pytest-mock faker
```

### 2. 运行测试（3分钟）

```bash
# 方式1: 使用测试脚本（推荐）
./run_module3_tests.sh all

# 方式2: 直接使用pytest
pytest tests/unit/ tests/integration/ tests/performance/ -v
```

### 3. 查看结果（1分钟）

测试通过后，你将看到：
- ✅ 95+测试用例全部通过
- 📊 覆盖率报告（预期≥80%）
- ⚡ 性能指标验证

---

## 📂 测试文件清单

```
tests/
├── conftest.py                          # ✅ 已扩展（新增7个fixtures）
├── unit/
│   ├── test_analysis_core.py           # ✅ 15+用例
│   ├── test_health_monitor.py          # ✅ 10用例
│   ├── test_reconnection_manager.py    # ✅ 8用例
│   ├── test_ws_manager.py              # ✅ 12用例
│   └── test_realtime_service.py        # ✅ 15+用例
├── integration/
│   ├── test_realtime_dataflow.py       # ✅ 8用例
│   ├── test_analysis_workflow.py       # ✅ 8用例
│   └── test_alert_integration.py       # ✅ 5用例
└── performance/
    └── test_realtime_performance.py    # ✅ 10用例
```

---

## 🎯 常用命令

```bash
# 仅运行单元测试（快速，不需要数据库）
pytest tests/unit/ -v

# 仅运行集成测试（需要TimescaleDB）
pytest tests/integration/ -v

# 仅运行性能测试
pytest tests/performance/ -v

# 生成覆盖率报告
./run_module3_tests.sh coverage

# 运行特定测试文件
pytest tests/unit/test_analysis_core.py -v

# 运行特定测试用例
pytest tests/unit/test_analysis_core.py::TestCalculateCorrelation::test_high_correlation -v
```

---

## 📊 预期结果

### 测试通过率
- **单元测试**: 60+用例，预期100%通过
- **集成测试**: 25+用例，预期100%通过
- **性能测试**: 10+用例，预期100%通过

### 覆盖率
- `analysis_core.py`: 92-95%
- `enhanced_ws_manager.py`: 88-92%
- `realtime_kline_service.py`: 85-90%
- **总体**: 85-90%

### 性能指标
- 消息处理吞吐量: >200消息/秒 ✅
- 分析延迟（60天数据）: <5秒 ✅
- 批量写入: >2000条/秒 ✅

---

## 🐛 故障排查

### 问题1: `ModuleNotFoundError: No module named 'pytest'`
```bash
pip install pytest pytest-cov pytest-mock faker
```

### 问题2: 数据库连接失败
```bash
docker-compose up -d timescaledb
bash scripts/setup_test_db.sh
```

### 问题3: 导入错误
```bash
# 确保在项目根目录
cd /Users/test/Downloads/hyperliquid-pair-hype-purr-analyze
pip install -e .
```

---

## 📚 详细文档

- 完整测试文档: [`tests/MODULE3_TEST_README.md`](tests/MODULE3_TEST_README.md)
- 测试总结: [`MODULE3_TEST_SUMMARY.md`](MODULE3_TEST_SUMMARY.md)
- 模块3设计: [`docs/MODULE3_REALTIME_DATAFLOW.md`](docs/MODULE3_REALTIME_DATAFLOW.md)

---

## ✅ 验收清单

运行以下命令验证测试套件：

```bash
# 1. 运行所有测试
./run_module3_tests.sh all

# 2. 生成覆盖率报告
./run_module3_tests.sh coverage

# 3. 查看覆盖率
open htmlcov_module3/index.html
```

如果看到：
- ✅ 所有测试通过
- ✅ 覆盖率≥80%
- ✅ 性能测试达标

恭喜！测试套件已成功实施！🎉

---

**快速帮助**: 如有问题，请查看 [`tests/MODULE3_TEST_README.md`](tests/MODULE3_TEST_README.md) 的详细故障排查部分。
