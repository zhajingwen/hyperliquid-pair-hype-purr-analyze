# TimescaleDB持久化与实时数据流 - 总体设计概览

## 📋 项目概述

为 `multi_coins3.py` 加密货币相关性分析系统添加企业级数据持久化和实时数据流能力。

### 核心目标

1. **减少API调用**：通过数据库缓存减少70%+的交易所API调用
2. **实时数据流**：集成WebSocket实时K线数据流，延迟<500ms
3. **历史数据支持**：提供90天滚动窗口的历史数据查询
4. **性能优化**：批量写入性能>1000条/秒
5. **高可用性**：Docker Compose一键部署，自动故障恢复

### 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 数据库 | TimescaleDB (PostgreSQL扩展) | 时序数据优化，自动分区 |
| 实时流 | strong-hyperliquid-websocket | WebSocket连接管理 |
| 容器化 | Docker Compose | 一键部署，资源隔离 |
| 数据库驱动 | psycopg 3.x | 连接池，异步支持 |
| 批量写入 | PostgreSQL COPY命令 | 10-100x性能提升 |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                   Hyperliquid Exchange                       │
│          REST API              WebSocket API                 │
└───────┬──────────────────────────────┬──────────────────────┘
        │                              │
        │ HTTP请求（增量补充）          │ WebSocket推送（实时）
        │                              │
        ▼                              ▼
┌──────────────────┐         ┌──────────────────────────────┐
│ multi_coins3.py  │         │ realtime_kline_service.py     │
│ (分析引擎)        │         │ ┌──────────────────────────┐ │
│ - 相关性分析      │         │ │  WebSocket Manager       │ │
│ - 协整检验        │         │ │  - 订阅管理              │ │
│ - Z-score检测    │         │ │  - 自动重连              │ │
│ - 套利信号        │         │ └──────────────────────────┘ │
└────────┬─────────┘         │ ┌──────────────────────────┐ │
         │                   │ │  Buffer Queue            │ │
         │ 查询/写入          │ │  - 异步缓冲              │ │
         │                   │ │  - 批量聚合              │ │
         ▼                   │ └──────────────────────────┘ │
┌─────────────────────────────┴──────────────────────────────┐
│                 utils/timescaledb.py                        │
│                 (数据库访问层)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Connection   │  │ Kline        │  │ Symbol       │     │
│  │ Pool Manager │  │ Repository   │  │ Metadata Repo│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────┬──────────────────────────────┘
                              │ psycopg连接池
                              │ COPY命令批量写入
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      TimescaleDB                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ klines表      │  │ symbol_      │  │ analysis_    │      │
│  │ (自动分区)    │  │ metadata表   │  │ results表    │      │
│  │ - 7天chunks   │  │ (币种管理)   │  │ (分析结果)   │      │
│  │ - 压缩策略    │  │ - 新币监控   │  │ - 套利信号   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 📦 模块拆分

系统按职责拆分为5个独立模块，每个模块可独立开发和测试：

### 模块1: 数据库基础设施 (Database Infrastructure)
**设计文档**: [MODULE1_DATABASE_INFRASTRUCTURE.md](MODULE1_DATABASE_INFRASTRUCTURE.md)

**职责**:
- TimescaleDB容器部署
- 数据库schema初始化
- 表结构和索引创建
- 数据保留和压缩策略

**交付物**:
- `docker-compose.yml` - 容器编排配置
- `init_timescaledb.sql` - SQL初始化脚本
- `.env.example` - 环境变量模板

**依赖**: 无（基础模块）

**测试策略**:
- Docker容器健康检查
- SQL脚本语法验证
- 表结构完整性测试

---

### 模块2: 数据库访问层 (Database Access Layer)
**设计文档**: [MODULE2_DATABASE_ACCESS_LAYER.md](MODULE2_DATABASE_ACCESS_LAYER.md)

**职责**:
- 连接池管理
- K线数据CRUD操作
- 币种元数据管理
- COPY命令批量写入优化

**交付物**:
- `utils/timescaledb.py` - 数据库访问层实现
- `tests/test_timescaledb.py` - 单元测试

**依赖**: 模块1（需要数据库运行）

**测试策略**:
- 连接池性能测试
- 批量写入性能基准测试（>1000条/秒）
- 数据一致性验证

---

### 模块3: 实时数据流 (Real-time Data Flow)
**设计文档**: [MODULE3_REALTIME_DATAFLOW.md](MODULE3_REALTIME_DATAFLOW.md)

**职责**:
- WebSocket连接管理
- 实时K线数据接收
- 缓冲队列和异步批量写入
- 动态币种订阅管理
- 新币种监控

**交付物**:
- `realtime_kline_service.py` - 实时数据服务
- `Dockerfile.realtime` - 实时服务容器
- `tests/test_realtime_service.py` - 集成测试

**依赖**: 模块1、模块2（需要数据库和访问层）

**测试策略**:
- WebSocket连接稳定性测试
- 数据完整性验证
- 断线重连测试
- 批量写入性能测试

---

### 模块4: 分析引擎集成 (Analysis Engine Integration)
**设计文档**: [MODULE4_ANALYSIS_ENGINE_INTEGRATION.md](MODULE4_ANALYSIS_ENGINE_INTEGRATION.md)

**职责**:
- `multi_coins3.py` 改造
- 数据下载方法增量更新
- 数据库查询集成
- 分析结果持久化

**交付物**:
- 修改后的 `multi_coins3.py`
- `tests/test_integration.py` - 端到端测试

**依赖**: 模块1、模块2（需要数据库和访问层）

**测试策略**:
- API调用次数验证（减少70%+）
- 数据覆盖率测试
- 分析结果准确性验证

---

### 模块5: 配置和部署 (Configuration & Deployment)
**设计文档**: [MODULE5_CONFIGURATION_DEPLOYMENT.md](MODULE5_CONFIGURATION_DEPLOYMENT.md)

**职责**:
- 环境变量配置管理
- 依赖包管理
- Docker Compose整合
- 部署文档和运维指南

**交付物**:
- `utils/config.py` - 配置管理
- `pyproject.toml` - 依赖声明
- `README_TIMESCALEDB.md` - 部署文档

**依赖**: 所有其他模块

**测试策略**:
- 一键部署验证
- 环境变量完整性检查
- 服务健康检查

## 📊 模块依赖关系

```
┌─────────────────────────────────────────────────┐
│         模块5: 配置和部署                        │
│         (Configuration & Deployment)            │
└────────────────┬────────────────────────────────┘
                 │ 依赖所有模块
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 模块3:   │ │ 模块4:   │ │          │
│ 实时数据流│ │ 分析引擎  │ │          │
└────┬─────┘ └────┬─────┘ │          │
     │            │        │          │
     │ 依赖       │ 依赖   │          │
     │            │        │          │
     └────────┬───┴────────┘          │
              │                       │
              ▼                       │
         ┌──────────┐                 │
         │ 模块2:   │                 │
         │ 数据库访问层│               │
         └────┬─────┘                 │
              │                       │
              │ 依赖                  │
              │                       │
              ▼                       │
         ┌──────────┐                 │
         │ 模块1:   │◄────────────────┘
         │ 数据库基础│
         └──────────┘
```

## 🚀 实施路线图

### 阶段1: 基础设施 (Week 1)
```yaml
优先级: P0 (必须完成)
模块: 模块1
预计时间: 30分钟
验收标准:
  - TimescaleDB容器成功启动
  - 所有表和索引创建成功
  - 数据保留策略生效
```

### 阶段2: 数据访问层 (Week 1)
```yaml
优先级: P0 (必须完成)
模块: 模块2
预计时间: 2小时
验收标准:
  - 连接池正常工作
  - COPY命令写入性能>1000条/秒
  - 单元测试覆盖率>80%
```

### 阶段3: 分析引擎集成 (Week 1)
```yaml
优先级: P0 (必须完成)
模块: 模块4
预计时间: 2小时
验收标准:
  - API调用次数减少70%+
  - 数据覆盖率>95%
  - 分析结果正确持久化
```

### 阶段4: 配置和部署 (Week 1)
```yaml
优先级: P0 (必须完成)
模块: 模块5
预计时间: 1小时
验收标准:
  - 一键部署成功
  - 文档完整可用
  - 健康检查通过
```

### 阶段5: 实时数据流 (Week 2+, 可选)
```yaml
优先级: P1 (增强功能)
模块: 模块3
预计时间: 6小时
验收标准:
  - WebSocket稳定运行24小时
  - 实时延迟<500ms
  - 新币种自动发现生效
```

## 📈 性能预期

| 指标 | 基准值 (无DB) | 目标值 (有DB) | 改善幅度 |
|------|--------------|--------------|----------|
| API调用次数/运行 | 150次 | <45次 | -70% |
| 数据加载时间 | 5-10分钟 | 1-2分钟 | -70% |
| 内存占用 | ~500MB | ~200MB | -60% |
| 数据库写入性能 | N/A | >1000条/秒 | N/A |
| WebSocket延迟 | N/A | <500ms | N/A |

## 🔍 质量标准

### 代码质量
- [ ] 所有数据库操作使用连接池
- [ ] 完整的异常处理和日志记录
- [ ] 数据库连接失败时优雅降级
- [ ] 代码风格与现有项目一致
- [ ] 单元测试覆盖率>80%

### 性能标准
- [ ] 批量写入性能>1000条/秒
- [ ] 单次查询响应时间<100ms
- [ ] WebSocket延迟<500ms
- [ ] 内存占用<200MB

### 运维标准
- [ ] Docker一键部署
- [ ] 健康检查配置完整
- [ ] 日志输出规范
- [ ] 监控指标完整

## 📚 文档结构

```
docs/
├── DESIGN_OVERVIEW.md                    # 本文档 (总体概览)
├── MODULE1_DATABASE_INFRASTRUCTURE.md    # 模块1设计文档
├── MODULE2_DATABASE_ACCESS_LAYER.md      # 模块2设计文档
├── MODULE3_REALTIME_DATAFLOW.md          # 模块3设计文档
├── MODULE4_ANALYSIS_ENGINE_INTEGRATION.md # 模块4设计文档
└── MODULE5_CONFIGURATION_DEPLOYMENT.md   # 模块5设计文档
```

## 🔗 相关资源

- [TimescaleDB官方文档](https://docs.timescale.com/)
- [strong-hyperliquid-websocket项目](https://github.com/zhajingwen/strong-hyperliquid-websocket)
- [Hyperliquid API文档](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api)
- [PostgreSQL COPY命令](https://www.postgresql.org/docs/current/sql-copy.html)

## 📝 变更历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2025-01-11 | v1.0 | 初始版本，模块化设计 |

---

**下一步**: 请按照模块编号顺序阅读各模块设计文档，并按照实施路线图执行开发和测试。
