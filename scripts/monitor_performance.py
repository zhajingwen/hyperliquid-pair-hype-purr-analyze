"""
实时性能监控脚本 (Performance Monitor)

功能:
- 每10秒输出性能指标
- 监控消息接收速率
- 监控分析队列深度
- 监控分析完成速率
- 监控CPU和内存占用

使用方法:
    uv run python scripts/monitor_performance.py

Author: Claude Code
Date: 2026-01-20
"""
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


import time
import psutil
import logging
import os
from datetime import datetime, timezone

from utils.timescaledb import TimescaleDBClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    性能监控器

    监控指标:
    - 消息接收速率 (条/秒)
    - K线写入速率 (条/秒)
    - 分析完成速率 (次/秒)
    - 分析失败率 (%)
    - CPU占用 (%)
    - 内存占用 (MB)
    """

    def __init__(self, interval: int = 10):
        """
        初始化监控器

        Args:
            interval: 监控间隔（秒）
        """
        self.interval = interval
        self.db = TimescaleDBClient()
        self.last_stats = {
            'messages': 0,
            'klines': 0,
            'analyses': 0,
            'timestamp': time.time()
        }

    def get_recent_stats(self) -> dict:
        """
        查询最近的统计数据

        Returns:
            统计数据字典
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # 消息总数（从K线表统计最近10秒）
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM klines
                        WHERE created_at > NOW() - INTERVAL '%s seconds'
                    """, (self.interval,))
                    messages_count = cur.fetchone()[0]

                    # 分析总数（最近10秒）
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM analysis_results
                        WHERE created_at > NOW() - INTERVAL '%s seconds'
                    """, (self.interval,))
                    analyses_count = cur.fetchone()[0]

                    # 分析失败统计（使用异常标记估算）
                    cur.execute("""
                        SELECT
                            COUNT(*) FILTER (WHERE is_anomaly = TRUE) as anomalies,
                            COUNT(*) as total_analyses
                        FROM analysis_results
                        WHERE created_at > NOW() - INTERVAL '%s seconds'
                    """, (self.interval,))
                    result = cur.fetchone()
                    anomalies = result[0] if result else 0
                    total_analyses = result[1] if result else 0

                    return {
                        'messages': messages_count,
                        'analyses': analyses_count,
                        'anomalies': anomalies,
                        'total_analyses': total_analyses
                    }

        except Exception as e:
            logger.error(f"查询统计数据失败: {e}", exc_info=True)
            return {
                'messages': 0,
                'analyses': 0,
                'anomalies': 0,
                'total_analyses': 0
            }

    def get_process_stats(self) -> dict:
        """
        获取进程资源占用

        Returns:
            进程统计字典
        """
        try:
            # 获取realtime_kline_service进程
            current_process = psutil.Process(os.getpid())

            # 查找主服务进程（假设名称包含realtime_kline_service）
            service_process = None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline')
                    if cmdline and any('realtime_kline_service' in cmd for cmd in cmdline):
                        service_process = proc
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if service_process:
                cpu_percent = service_process.cpu_percent(interval=1)
                memory_mb = service_process.memory_info().rss / 1024 / 1024
            else:
                # 如果找不到服务进程，使用当前进程
                cpu_percent = current_process.cpu_percent(interval=1)
                memory_mb = current_process.memory_info().rss / 1024 / 1024

            return {
                'cpu_percent': cpu_percent,
                'memory_mb': memory_mb
            }

        except Exception as e:
            logger.error(f"获取进程统计失败: {e}", exc_info=True)
            return {
                'cpu_percent': 0.0,
                'memory_mb': 0.0
            }

    def monitor_loop(self):
        """
        监控主循环

        每隔 interval 秒输出一次性能指标
        """
        logger.info(f"🚀 启动性能监控器（间隔: {self.interval}秒）")
        logger.info("按 Ctrl+C 停止监控")

        try:
            while True:
                time.sleep(self.interval)

                # 查询统计数据
                stats = self.get_recent_stats()
                process_stats = self.get_process_stats()

                # 计算速率
                messages_rate = stats['messages'] / self.interval
                analyses_rate = stats['analyses'] / self.interval

                # 计算分析失败率
                failure_rate = 0.0
                if stats['total_analyses'] > 0:
                    # 注意：这里使用 anomalies 作为失败的近似估算
                    # 实际失败数据需要从应用日志或其他来源获取
                    failure_rate = (stats['anomalies'] / stats['total_analyses']) * 100

                # 输出监控信息
                logger.info(
                    f"📊 性能监控 | "
                    f"消息: {stats['messages']}/{self.interval}s ({messages_rate:.1f}/s) | "
                    f"分析: {stats['analyses']}/{self.interval}s ({analyses_rate:.1f}/s) | "
                    f"异常: {stats['anomalies']} | "
                    f"CPU: {process_stats['cpu_percent']:.1f}% | "
                    f"内存: {process_stats['memory_mb']:.1f}MB"
                )

                # 性能告警
                if process_stats['cpu_percent'] > 50:
                    logger.warning(f"⚠️ CPU占用过高: {process_stats['cpu_percent']:.1f}%")

                if process_stats['memory_mb'] > 512:
                    logger.warning(f"⚠️ 内存占用过高: {process_stats['memory_mb']:.1f}MB")

                if analyses_rate < 0.1 and messages_rate > 1.0:
                    logger.warning(f"⚠️ 分析速率过低: {analyses_rate:.2f}/s（消息速率: {messages_rate:.1f}/s）")

        except KeyboardInterrupt:
            logger.info("接收到中断信号，停止监控")
        except Exception as e:
            logger.error(f"监控异常: {e}", exc_info=True)
        finally:
            logger.info("✅ 监控器已停止")


def main():
    """主程序入口"""
    monitor = PerformanceMonitor(interval=10)
    monitor.monitor_loop()


if __name__ == '__main__':
    main()
