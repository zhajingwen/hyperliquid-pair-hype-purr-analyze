"""
WebSocket Ping 修复 - 最小化方案

问题：第三方库 hyperliquid 的 send_ping() 在连接关闭时崩溃
修复：仅添加 try-except 捕获异常，防止线程崩溃

Author: Claude Code
Date: 2026-01-25
"""

import json
import logging
from hyperliquid.websocket_manager import WebsocketManager

logger = logging.getLogger(__name__)

# 保存原始方法（用于调试）
_original_send_ping = WebsocketManager.send_ping


def _safe_send_ping(self):
    """修复版 send_ping：添加异常捕获"""
    while not self.stop_event.wait(50):
        if not self.ws.keep_running:
            break
        logging.debug("Websocket sending ping")
        try:
            self.ws.send(json.dumps({"method": "ping"}))
        except Exception as e:
            logger.warning(f"Websocket ping 失败: {e}")
            break
    logging.debug("Websocket ping sender stopped")


# 应用补丁
WebsocketManager.send_ping = _safe_send_ping
logger.info("✅ WebSocket ping 修复已应用")
