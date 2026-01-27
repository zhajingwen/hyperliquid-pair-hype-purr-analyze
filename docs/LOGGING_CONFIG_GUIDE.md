# 统一日志配置使用指南

## 概述

项目已实现统一的日志配置管理，**导入即用**，无需手动初始化。

## 核心特性

- ✅ **导入即用** - 无需手动调用初始化函数
- ✅ 集中化日志配置管理
- ✅ 支持环境变量配置
- ✅ 控制台 + 文件双输出
- ✅ 日志文件自动轮转（100MB，保留5个备份）
- ✅ 为第三方库降低日志级别
- ✅ 防止重复初始化

## 使用方法

### 方式1：直接使用全局 logger（推荐）

```python
from utils.logging_config import logger

logger.info("这是一条日志")
logger.debug("调试信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### 方式2：获取自定义名称的 logger

```python
from utils.logging_config import get_logger

logger = get_logger(__name__)  # 使用模块名
logger.info("这是一条日志")
```

### 示例代码

**主程序（`realtime_kline_service_hype.py`）：**
```python
import os
import sys
# ... 其他标准库导入

from hyperliquid.info import Info
import hyperliquid.utils.constants as constants

# 直接导入 logger
from utils.logging_config import get_logger
from utils.enhanced_ws_manager import EnhancedWebSocketManager
from utils.timescaledb import TimescaleDBClient

# 获取 logger
logger = get_logger(__name__)

# 使用 logger
logger.info("服务启动")
```

**工具模块（`utils/analysis_core.py`）：**
```python
import logging
from utils.logging_config import get_logger

logger = get_logger(__name__)

def some_function():
    logger.info("处理中...")
```

## 环境变量配置

通过环境变量灵活配置日志（在导入模块前设置）：

```bash
# 设置全局日志级别
export LOG_LEVEL=INFO          # DEBUG/INFO/WARNING/ERROR/CRITICAL

# 分别设置控制台和文件日志级别
export CONSOLE_LOG_LEVEL=INFO  # 控制台日志级别
export FILE_LOG_LEVEL=DEBUG    # 文件日志级别（更详细）

# 设置日志文件路径（不设置则只输出到控制台）
export LOG_FILE=logs/app.log

# 示例：开发环境（详细日志 + 文件记录）
export LOG_LEVEL=DEBUG
export LOG_FILE=logs/dev.log

# 示例：生产环境（精简日志）
export LOG_LEVEL=INFO
export CONSOLE_LOG_LEVEL=WARNING
export FILE_LOG_LEVEL=INFO
export LOG_FILE=logs/production.log
```

### 在代码中设置环境变量

如果需要在代码中设置环境变量，必须在导入 `utils.logging_config` 之前：

```python
import os

# 设置环境变量（必须在导入前）
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['LOG_FILE'] = 'logs/app.log'

# 然后导入日志模块（自动初始化）
from utils.logging_config import logger

logger.info("日志系统已初始化")
```

## 日志级别说明

| 级别 | 值 | 用途 | 典型场景 |
|------|-----|------|----------|
| DEBUG | 10 | 详细的调试信息 | 开发调试、问题排查 |
| INFO | 20 | 一般信息 | 程序正常运行、重要事件记录 |
| WARNING | 30 | 警告信息 | 潜在问题、配置缺失 |
| ERROR | 40 | 错误信息 | 可恢复的错误 |
| CRITICAL | 50 | 严重错误 | 系统崩溃、数据丢失 |

**默认配置：**
- 控制台和文件均为 `INFO` 级别
- 不显示 `DEBUG` 日志（减少噪音）

## 日志文件

### 存储位置

所有日志文件存放在 `logs/` 目录（自动创建）：

```
logs/
├── test_logging.log       # 测试日志
├── app.log               # 应用日志
└── ...
```

### 轮转规则

- 单个文件最大 **100MB**
- 保留 **5 个备份**（如 `app.log`, `app.log.1`, `app.log.2`, ...）
- 超过大小自动轮转，旧文件自动重命名

### 日志格式

```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

示例输出：
```
2026-01-27 23:43:51 - __main__ - INFO - 服务启动成功
2026-01-27 23:43:52 - utils.config - WARNING - 未配置环境变量
```

## 验证测试

运行测试脚本验证配置：

```bash
python test_logging_config.py
```

预期输出：
- ✓ 不显示 DEBUG 日志（级别为 INFO 时）
- ✓ 显示 INFO、WARNING、ERROR 日志
- ✓ 日志文件成功创建
- ✓ 多模块日志正常工作

## 配置说明

### 默认配置

在 `utils/logging_config.py` 中：

```python
# 日志级别配置（从环境变量读取，默认 INFO）
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
CONSOLE_LOG_LEVEL = os.getenv('CONSOLE_LOG_LEVEL', LOG_LEVEL).upper()
FILE_LOG_LEVEL = os.getenv('FILE_LOG_LEVEL', LOG_LEVEL).upper()

# 日志文件配置（可选，不设置则只输出到控制台）
LOG_FILE = os.getenv('LOG_FILE')

# 日志文件轮转配置
MAX_BYTES = 100 * 1024 * 1024  # 100MB
BACKUP_COUNT = 5  # 保留5个备份
```

### 第三方库日志级别

为避免第三方库日志过多，已配置：

```python
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('websocket').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('hyperliquid').setLevel(logging.INFO)
```

如需调整更多库，在 `utils/logging_config.py` 的 `_init_logging()` 函数中添加。

## 常见问题

### Q1: 日志级别不生效？

**A:** 确保环境变量在导入模块前设置：

```python
import os

# ✅ 正确：在导入前设置
os.environ['LOG_LEVEL'] = 'DEBUG'
from utils.logging_config import logger

# ❌ 错误：在导入后设置（不生效）
from utils.logging_config import logger
os.environ['LOG_LEVEL'] = 'DEBUG'
```

### Q2: 日志文件没有创建？

**A:** 检查是否设置了 `LOG_FILE` 环境变量：

```bash
export LOG_FILE=logs/app.log
python your_script.py
```

或在代码中设置：

```python
import os
os.environ['LOG_FILE'] = 'logs/app.log'
from utils.logging_config import logger
```

### Q3: 第三方库日志太多？

**A:** 在 `utils/logging_config.py` 中添加配置：

```python
logging.getLogger('library_name').setLevel(logging.WARNING)
```

### Q4: 如何在不同服务使用不同的日志文件？

**A:** 通过环境变量启动：

```bash
# 服务1
LOG_FILE=logs/service1.log python service1.py

# 服务2
LOG_FILE=logs/service2.log python service2.py
```

## 最佳实践

### 1. 使用合适的日志级别

```python
# 调试信息（开发时使用）
logger.debug("变量值: x=%s, y=%s", x, y)

# 重要事件（程序正常运行）
logger.info("服务启动成功")
logger.info("处理完成: %s 条记录", count)

# 警告（潜在问题）
logger.warning("配置缺失，使用默认值")
logger.warning("重试 %d 次", retry_count)

# 错误（可恢复）
logger.error("处理失败: %s", e, exc_info=True)

# 严重错误（系统崩溃）
logger.critical("数据库连接失败，服务无法启动")
```

### 2. 使用参数化日志消息

```python
# ✅ 推荐：延迟字符串格式化（性能更好）
logger.info("处理完成: %s, 耗时: %.2fs", symbol, elapsed)

# ❌ 不推荐：提前格式化（即使日志级别不输出也会格式化）
logger.info(f"处理完成: {symbol}, 耗时: {elapsed:.2f}s")
```

### 3. 记录异常堆栈

```python
try:
    risky_operation()
except Exception as e:
    # 使用 exc_info=True 记录完整堆栈
    logger.error("操作失败: %s", e, exc_info=True)
```

### 4. 使用模块名称

```python
# ✅ 推荐：使用 __name__（便于追踪日志来源）
logger = get_logger(__name__)

# ❌ 不推荐：使用固定名称
logger = get_logger('MyLogger')
```

## 迁移说明

### 从旧版迁移

**旧版（需要手动初始化）：**
```python
from utils.logging_config import setup_logging, get_logger
setup_logging(level='INFO', log_file='logs/app.log')
logger = get_logger(__name__)
```

**新版（导入即用）：**
```python
from utils.logging_config import get_logger
logger = get_logger(__name__)
```

或直接使用全局 logger：
```python
from utils.logging_config import logger
```

### 环境变量配置

启动时设置环境变量：
```bash
export LOG_LEVEL=INFO
export LOG_FILE=logs/app.log
python your_script.py
```

## 技术细节

### 自动初始化机制

`utils/logging_config.py` 在模块加载时自动调用 `_init_logging()` 初始化日志系统：

```python
def _init_logging():
    """初始化日志系统（模块加载时自动调用）"""
    # ... 初始化逻辑

# 模块加载时自动初始化
_init_logging()
```

### 防重复初始化

通过清除已有 handlers 防止重复初始化：

```python
root_logger = logging.getLogger()
root_logger.handlers.clear()  # 清除现有 handlers
```

### 目录结构

```
project/
├── utils/
│   └── logging_config.py    # 统一日志配置模块（自动初始化）
├── logs/                     # 日志文件目录（自动创建）
│   ├── app.log
│   └── ...
├── realtime_kline_service_hype.py
└── test_logging_config.py   # 测试脚本
```

## 更新日志

- **2026-01-27 v2**: 简化使用方式，导入即用，无需手动初始化
  - 移除 `setup_logging()` 调用要求
  - 模块加载时自动初始化
  - 通过环境变量配置
  - 更简洁的代码

- **2026-01-27 v1**: 初始版本，实现统一日志配置管理
  - 创建 `utils/logging_config.py`
  - 修改 20 个文件使用统一配置
  - 支持环境变量配置
  - 添加测试脚本

## 快速参考

### 基本使用

```python
# 导入
from utils.logging_config import logger

# 使用
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告")
logger.error("错误")
logger.critical("严重错误")
```

### 环境变量

```bash
export LOG_LEVEL=INFO           # 日志级别
export LOG_FILE=logs/app.log    # 日志文件
export CONSOLE_LOG_LEVEL=INFO   # 控制台级别
export FILE_LOG_LEVEL=DEBUG     # 文件级别
```

### 测试

```bash
python test_logging_config.py
```
