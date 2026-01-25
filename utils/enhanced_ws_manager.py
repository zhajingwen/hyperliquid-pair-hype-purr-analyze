"""
增强型 WebSocket 连接管理器

设计灵感来源: https://github.com/zhajingwen/strong-hyperliquid-websocket
核心改进:
- 双重健康检测（底层连接 + 应用层心跳）
- 指数退避重连策略
- 完整的状态机管理
- 线程安全设计
- 可观测性（统计信息和健康报告）

Author: Claude Code (基于 strong-hyperliquid-websocket 设计)
Date: 2026-01-19
"""

import time
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone
from hyperliquid.info import Info
from hyperliquid.websocket_manager import WebsocketManager
import hyperliquid.utils.constants as constants

# 导入 WebSocket Monkey Patch（修复 ping 线程异常）
try:
    from utils.websocket_patch import apply_websocket_patch
    # Patch 会在导入时自动应用
except ImportError as e:
    logging.warning(f"WebSocket Monkey Patch 导入失败: {e}，可能导致 ping 线程异常")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# =====================================================
# 状态枚举
# =====================================================

class ConnectionState(Enum):
    """WebSocket连接状态"""
    DISCONNECTED = "disconnected"  # 未连接
    CONNECTING = "connecting"      # 连接中
    CONNECTED = "connected"        # 已连接
    RECONNECTING = "reconnecting"  # 重连中
    FAILED = "failed"              # 连接失败


# =====================================================
# 健康监控器
# =====================================================

class HealthMonitor:
    """
    健康监控器（应用层心跳）

    功能:
    - 追踪最后消息接收时间
    - 检测数据流中断（假活状态）
    - 双阈值告警（警告 + 超时）

    设计参考: strong-hyperliquid-websocket 的 HealthMonitor
    """

    def __init__(self, timeout: int = 30, warning_threshold: int = 15):
        """
        初始化健康监控器

        Args:
            timeout: 超时阈值（秒），超过此时间未收到数据判定为假活
            warning_threshold: 警告阈值（秒），超过此时间触发警告日志
        """
        self.timeout = timeout
        self.warning_threshold = warning_threshold
        self.last_message_time = time.time()
        self.message_count = 0
        self._lock = threading.Lock()

    def on_message(self):
        """更新最后消息接收时间"""
        with self._lock:
            self.last_message_time = time.time()
            self.message_count += 1

    def is_alive(self) -> tuple[bool, float]:
        """
        检查连接是否存活

        Returns:
            (is_alive, idle_seconds): 是否存活，空闲时长（秒）
        """
        with self._lock:
            idle_time = time.time() - self.last_message_time

            if idle_time > self.timeout:
                return False, idle_time
            elif idle_time > self.warning_threshold:
                logger.warning(f"健康检查警告: {idle_time:.1f}秒未收到数据")

            return True, idle_time

    def get_health_percentage(self) -> float:
        """获取健康度百分比（0-100%）"""
        _, idle_time = self.is_alive()
        return max(0, 100 - (idle_time / self.timeout * 100))


# =====================================================
# 重连管理器
# =====================================================

class ReconnectionManager:
    """
    重连管理器（指数退避策略）

    特性:
    - 指数退避: 1s → 2s → 4s → 8s → 16s → 32s → 60s
    - 随机抖动: ±25% (防止雷鸣羊群效应)
    - 可配置最大延迟和重试次数

    设计参考: strong-hyperliquid-websocket 的 ReconnectionManager
    """

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        max_retries: Optional[int] = None
    ):
        """
        初始化重连管理器

        Args:
            initial_delay: 初始延迟（秒）
            max_delay: 最大延迟（秒）
            multiplier: 延迟递增因子
            max_retries: 最大重试次数（None = 无限重试）
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.max_retries = max_retries
        self.retry_count = 0
        self.total_reconnections = 0

    def get_delay(self) -> float:
        """
        计算下次重连延迟（指数退避 + 随机抖动）

        Returns:
            延迟时间（秒）
        """
        import random

        # 指数退避
        delay = self.initial_delay * (self.multiplier ** self.retry_count)
        delay = min(delay, self.max_delay)

        # 随机抖动 ±25%
        jitter = delay * 0.25
        delay += random.uniform(-jitter, jitter)

        return max(0.1, delay)  # 最小延迟0.1秒

    def should_retry(self) -> bool:
        """判断是否应该继续重试"""
        if self.max_retries is None:
            return True
        return self.retry_count < self.max_retries

    def record_attempt(self):
        """记录一次重连尝试"""
        self.retry_count += 1
        self.total_reconnections += 1

    def reset(self):
        """重置重试计数器（连接成功后调用）"""
        self.retry_count = 0


# =====================================================
# 增强型 WebSocket 管理器
# =====================================================

class EnhancedWebSocketManager:
    """
    增强型 WebSocket 连接管理器

    核心功能:
    - 双重健康检测（底层连接 + 应用层心跳）
    - 自动重连（指数退避策略）
    - 状态机管理（DISCONNECTED → CONNECTING → CONNECTED → RECONNECTING → FAILED）
    - 线程安全（递归锁保护）
    - 可观测性（统计信息、健康报告）

    设计参考: https://github.com/zhajingwen/strong-hyperliquid-websocket
    作者: Claude Code (集成改进)
    """

    def __init__(
        self,
        subscriptions: List[Dict],
        message_callback: Callable[[Dict], None],
        on_state_change: Optional[Callable[[ConnectionState, Optional[Exception]], None]] = None,
        timeout: int = 30,
        skip_disconnects: bool = False
    ):
        """
        初始化增强型 WebSocket 管理器

        Args:
            subscriptions: 订阅列表，格式: [{"type": "candle", "coin": "BTC", "interval": "5m"}, ...]
            message_callback: 消息回调函数，签名: (msg: Dict) -> None
            on_state_change: 状态变化回调，签名: (state: ConnectionState, error: Optional[Exception]) -> None
            timeout: 数据流超时（秒），默认30秒
            skip_disconnects: 是否跳过断连处理（用于测试）
        """
        self.subscriptions = subscriptions
        self.message_callback = message_callback
        self.on_state_change_callback = on_state_change
        self.timeout = timeout
        self.skip_disconnects = skip_disconnects

        # 状态管理
        self.state = ConnectionState.DISCONNECTED
        self.state_lock = threading.RLock()

        # 动态订阅管理（修复：新币种监控失效）
        self.subscriptions_lock = threading.RLock()
        self.active_subscriptions = set()  # 去重已激活订阅

        # Hyperliquid SDK 组件
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.ws_manager: Optional[WebsocketManager] = None
        self.ws_ready_event = threading.Event()

        # 健康监控
        self.health_monitor = HealthMonitor(timeout=timeout)

        # 重连管理
        self.reconnection_manager = ReconnectionManager()

        # 停止事件
        self.stop_event = threading.Event()

        # 统计信息
        self.start_time = time.time()
        self.last_error: Optional[Exception] = None

        logger.info(f"增强型WebSocket管理器初始化完成 | 订阅数: {len(subscriptions)} | 超时: {timeout}秒")

    def _update_state(self, new_state: ConnectionState, error: Optional[Exception] = None):
        """更新连接状态（线程安全）"""
        with self.state_lock:
            old_state = self.state
            self.state = new_state
            self.last_error = error

            logger.info(f"状态转换: {old_state.value} → {new_state.value}")

            if self.on_state_change_callback:
                try:
                    self.on_state_change_callback(new_state, error)
                except Exception as e:
                    logger.error(f"状态回调执行失败: {e}", exc_info=True)

    def _is_connected(self) -> bool:
        """检查 WebSocket 是否已连接"""
        if not self.info.ws_manager:
            return False

        try:
            # 检查底层连接状态
            return (
                hasattr(self.info.ws_manager, 'ws') and
                self.info.ws_manager.ws is not None and
                self.info.ws_manager.ws.keep_running
            )
        except Exception:
            return False

    def _wrapped_callback(self, msg: Dict):
        """封装的消息回调（包含健康监控）"""
        try:
            # 更新健康监控
            self.health_monitor.on_message()

            # 调用用户回调
            self.message_callback(msg)
        except Exception as e:
            logger.error(f"消息回调执行失败: {e}", exc_info=True)

    def _connect(self):
        """建立 WebSocket 连接"""
        try:
            self._update_state(ConnectionState.CONNECTING)

            # 使用锁保护订阅列表访问（修复：动态订阅支持）
            with self.subscriptions_lock:
                subscriptions_to_use = list(self.subscriptions)
                # 重建active_subscriptions集合（去重）
                self.active_subscriptions.clear()

            # 使用 Info.subscribe() 方法订阅所有频道
            for subscription in subscriptions_to_use:
                self.info.subscribe(subscription, self._wrapped_callback)
                # 记录订阅（用于去重）
                sub_key = (subscription.get('type'), subscription.get('coin'), subscription.get('interval'))
                self.active_subscriptions.add(sub_key)

            # 等待连接就绪
            self.ws_ready_event.set()

            # 验证连接
            time.sleep(1)  # 给WebSocket一点时间完成握手
            if self._is_connected():
                self._update_state(ConnectionState.CONNECTED)
                self.reconnection_manager.reset()
                logger.info(f"✅ WebSocket连接成功 | 订阅数: {len(self.active_subscriptions)}")
            else:
                raise ConnectionError("WebSocket连接验证失败")

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}", exc_info=True)
            self._update_state(ConnectionState.FAILED, e)
            raise

    def _force_cleanup_connection(self):
        """
        强制清理WebSocket连接（修复连接泄漏问题）

        清理步骤（5步确定性清理）:
        1. 停止WebSocket运行循环
        2. 调用官方disconnect方法
        3. 强制关闭底层连接
        4. 显式终止ping线程
        5. 清除引用确保GC回收

        设计原则:
        - 每步独立try-except，互不影响
        - 详细日志记录每步清理状态（可观测性）
        - 部分失败不阻塞重连（异常容忍）
        """
        logger.info("开始强制清理WebSocket连接...")
        cleanup_status = []

        # Step 1: 停止WebSocket运行循环
        try:
            if self.info.ws_manager and hasattr(self.info.ws_manager, 'ws') and self.info.ws_manager.ws:
                self.info.ws_manager.ws.keep_running = False
                cleanup_status.append("✅ Step1: 停止运行循环")
            else:
                cleanup_status.append("⏭️ Step1: 无运行循环")
        except Exception as e:
            cleanup_status.append(f"❌ Step1: {e}")
            logger.warning(f"停止运行循环失败: {e}")

        # Step 2: 调用官方disconnect方法
        try:
            if self.info.ws_manager:
                self.info.disconnect_websocket()
                cleanup_status.append("✅ Step2: 官方disconnect成功")
            else:
                cleanup_status.append("⏭️ Step2: 无ws_manager")
        except Exception as e:
            cleanup_status.append(f"❌ Step2: {e}")
            logger.warning(f"官方disconnect失败: {e}")

        # Step 3: 强制关闭底层连接
        try:
            if self.info.ws_manager and hasattr(self.info.ws_manager, 'ws') and self.info.ws_manager.ws:
                self.info.ws_manager.ws.close()
                cleanup_status.append("✅ Step3: 底层连接已关闭")
            else:
                cleanup_status.append("⏭️ Step3: 无底层连接")
        except Exception as e:
            cleanup_status.append(f"❌ Step3: {e}")
            logger.warning(f"关闭底层连接失败: {e}")

        # Step 4: 显式终止ping线程（如果存在）
        try:
            if self.info.ws_manager and hasattr(self.info.ws_manager, 'ping_thread'):
                ping_thread = self.info.ws_manager.ping_thread
                if ping_thread and ping_thread.is_alive():
                    ping_thread.join(timeout=2.0)
                    if ping_thread.is_alive():
                        cleanup_status.append("⚠️ Step4: ping线程未在2秒内退出")
                    else:
                        cleanup_status.append("✅ Step4: ping线程已终止")
                else:
                    cleanup_status.append("⏭️ Step4: 无活跃ping线程")
            else:
                cleanup_status.append("⏭️ Step4: 无ping线程")
        except Exception as e:
            cleanup_status.append(f"❌ Step4: {e}")
            logger.warning(f"终止ping线程失败: {e}")

        # Step 5: 清除引用确保GC回收
        try:
            if self.info.ws_manager:
                self.info.ws_manager = None
                cleanup_status.append("✅ Step5: 引用已清除")
            else:
                cleanup_status.append("⏭️ Step5: 无需清除")
        except Exception as e:
            cleanup_status.append(f"❌ Step5: {e}")
            logger.warning(f"清除引用失败: {e}")

        # 等待资源释放
        time.sleep(0.5)

        # 汇总日志
        logger.info(f"强制清理完成: {' | '.join(cleanup_status)}")

    def add_subscriptions(self, new_subscriptions: List[Dict]) -> bool:
        """
        动态添加订阅（运行时热更新）

        Args:
            new_subscriptions: 新增订阅列表，格式: [{"type": "candle", "coin": "NEWCOIN", "interval": "5m"}, ...]

        Returns:
            bool: 订阅是否成功

        功能:
        - 去重：避免重复订阅相同频道
        - 线程安全：使用锁保护订阅列表
        - 即时订阅：连接已建立时立即调用Info.subscribe()
        - 延迟订阅：连接未建立时添加到列表，重连时自动订阅
        """
        if not new_subscriptions:
            return True

        try:
            added_count = 0
            skipped_count = 0

            with self.subscriptions_lock:
                for subscription in new_subscriptions:
                    # 生成订阅唯一键（去重）
                    sub_key = (
                        subscription.get('type'),
                        subscription.get('coin'),
                        subscription.get('interval')
                    )

                    # 检查是否已订阅
                    if sub_key in self.active_subscriptions:
                        skipped_count += 1
                        logger.debug(f"跳过重复订阅: {sub_key}")
                        continue

                    # 添加到订阅列表
                    self.subscriptions.append(subscription)

                    # 如果连接已建立，立即订阅
                    if self._is_connected():
                        try:
                            self.info.subscribe(subscription, self._wrapped_callback)
                            self.active_subscriptions.add(sub_key)
                            added_count += 1
                            logger.info(f"✅ 动态订阅成功: {subscription.get('coin')} @ {subscription.get('interval')}")
                        except Exception as e:
                            logger.error(f"动态订阅失败: {sub_key} | {e}")
                            # 订阅失败，从列表移除
                            self.subscriptions.remove(subscription)
                    else:
                        # 连接未建立，只添加到列表（重连时自动订阅）
                        added_count += 1
                        logger.info(f"📋 延迟订阅已添加: {subscription.get('coin')} @ {subscription.get('interval')} (重连时生效)")

            logger.info(
                f"动态订阅完成: 新增 {added_count} 个订阅，跳过 {skipped_count} 个重复订阅 | "
                f"总订阅数: {len(self.subscriptions)}"
            )
            return True

        except Exception as e:
            logger.error(f"动态添加订阅失败: {e}", exc_info=True)
            return False

    def _reconnect(self):
        """重连逻辑（指数退避策略）"""
        self._update_state(ConnectionState.RECONNECTING)

        while self.reconnection_manager.should_retry() and not self.stop_event.is_set():
            self.reconnection_manager.record_attempt()
            delay = self.reconnection_manager.get_delay()

            logger.info(
                f"⏳ 准备重连 (第{self.reconnection_manager.retry_count}次) | "
                f"延迟: {delay:.2f}秒"
            )

            self.stop_event.wait(delay)

            if self.stop_event.is_set():
                break

            try:
                # 强制清理旧连接（修复连接泄漏）
                if self.info.ws_manager:
                    self._force_cleanup_connection()

                # 重新创建 Info 对象（会自动创建新的 WebSocket 连接）
                self.info = Info(constants.MAINNET_API_URL, skip_ws=False)

                # 尝试重连
                self._connect()
                logger.info("✅ WebSocket重连成功")
                return

            except Exception as e:
                logger.error(f"重连失败: {e}")

        # 重试次数耗尽
        logger.error("重连失败: 达到最大重试次数")
        self._update_state(ConnectionState.FAILED)

    def _monitor_health(self):
        """健康监控主循环"""
        logger.info("健康监控线程已启动")

        while not self.stop_event.is_set():
            try:
                # 等待连接就绪
                if not self.ws_ready_event.wait(timeout=5):
                    continue

                # 检查底层连接
                if not self._is_connected():
                    logger.warning("底层连接已断开，触发重连")
                    self._reconnect()
                    continue

                # 检查应用层心跳（假活检测）
                is_alive, idle_time = self.health_monitor.is_alive()
                if not is_alive:
                    logger.warning(f"假活状态检测: {idle_time:.1f}秒未收到数据，触发重连")
                    self._reconnect()
                    continue

                # 定期健康报告（每60秒）
                if int(time.time() - self.start_time) % 60 == 0:
                    self._log_health_report()

            except Exception as e:
                logger.error(f"健康监控异常: {e}", exc_info=True)

            time.sleep(5)  # 每5秒检查一次

        logger.info("健康监控线程已停止")

    def _log_health_report(self):
        """记录健康报告"""
        stats = self.get_stats()
        logger.info(
            f"📊 健康报告 | "
            f"健康度: {stats['health_percentage']:.1f}% | "
            f"消息数: {stats['message_count']} | "
            f"重连次数: {stats['total_reconnections']} | "
            f"运行时长: {stats['uptime_seconds']:.0f}秒"
        )

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'state': self.state.value,
            'health_percentage': self.health_monitor.get_health_percentage(),
            'message_count': self.health_monitor.message_count,
            'total_reconnections': self.reconnection_manager.total_reconnections,
            'uptime_seconds': time.time() - self.start_time,
            'last_error': str(self.last_error) if self.last_error else None
        }

    def start(self):
        """启动 WebSocket 服务（阻塞运行）"""
        logger.info("🚀 启动增强型WebSocket管理器...")

        try:
            # 建立初始连接
            self._connect()

            # 启动健康监控线程
            monitor_thread = threading.Thread(
                target=self._monitor_health,
                daemon=True,
                name="ws-health-monitor"
            )
            monitor_thread.start()

            # 主线程阻塞等待
            self.stop_event.wait()

        except KeyboardInterrupt:
            logger.info("接收到中断信号，停止服务...")
        except Exception as e:
            logger.error(f"服务异常: {e}", exc_info=True)
        finally:
            self.stop()

    def stop(self):
        """停止 WebSocket 服务"""
        logger.info("停止WebSocket服务...")
        self.stop_event.set()

        # 强制清理连接（修复连接泄漏）
        if self.info.ws_manager:
            self._force_cleanup_connection()

        self._update_state(ConnectionState.DISCONNECTED)
        logger.info("WebSocket服务已停止")


# =====================================================
# 导出接口
# =====================================================

__all__ = [
    'EnhancedWebSocketManager',
    'ConnectionState',
    'HealthMonitor',
    'ReconnectionManager'
]
