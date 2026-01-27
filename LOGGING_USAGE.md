# 日志配置使用说明（极简版）

## 最简单的使用方式

```python
from utils.logging_config import logger

logger.info("这是一条日志")
logger.debug("调试信息")
logger.warning("警告信息")
logger.error("错误信息")
```

**就这么简单！只需要一行导入！** ⚡

## 配置日志级别

### 通过环境变量（推荐）

```bash
# 启动程序前设置
export LOG_LEVEL=INFO
export LOG_FILE=logs/app.log
python your_script.py
```

### 可用的环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 全局日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL） |
| `LOG_FILE` | 无 | 日志文件路径（不设置则只输出到控制台） |
| `CONSOLE_LOG_LEVEL` | 同 `LOG_LEVEL` | 控制台日志级别 |
| `FILE_LOG_LEVEL` | 同 `LOG_LEVEL` | 文件日志级别 |

## 示例

### 开发环境（详细日志）

```bash
export LOG_LEVEL=DEBUG
export LOG_FILE=logs/dev.log
python realtime_kline_service_hype.py
```

### 生产环境（精简日志）

```bash
export LOG_LEVEL=INFO
export LOG_FILE=logs/production.log
python realtime_kline_service_hype.py
```

### 只输出到控制台

```bash
export LOG_LEVEL=INFO
# 不设置 LOG_FILE
python realtime_kline_service_hype.py
```

## 代码示例

### 主程序

```python
import os
import sys

from utils.logging_config import logger
from utils.enhanced_ws_manager import EnhancedWebSocketManager

logger.info("服务启动")
```

### 工具模块

```python
from utils.logging_config import logger

def process_data():
    logger.info("处理数据中...")
```

## 对比：优化前 vs 优化后

**优化前：**
```python
import logging
from utils.logging_config import get_logger

logger = get_logger(__name__)  # 需要这一行
logger.info("日志")
```

**优化后：**
```python
from utils.logging_config import logger  # 只需要这一行！

logger.info("日志")
```

## 测试

```bash
python test_logging_config.py
```

## 详细文档

查看完整文档：[docs/LOGGING_CONFIG_GUIDE.md](docs/LOGGING_CONFIG_GUIDE.md)
