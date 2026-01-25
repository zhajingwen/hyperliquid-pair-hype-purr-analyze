"""
WebSocket Monkey Patch - 修复 Hyperliquid WebSocket ping 线程异常

问题描述:
- 第三方库 hyperliquid.websocket_manager.WebsocketManager.send_ping() 
  在连接关闭时仍尝试发送 ping，导致 WebSocketConnectionClosedException

修复方案:
- 在发送 ping 前检查连接状态
- 捕获异常防止线程崩溃

影响范围:
- 仅修复 send_ping 方法，不影响其他功能

Author: Claude Code
Date: 2026-01-25
"""

import json
import logging
from hyperliquid.websocket_manager import WebsocketManager

logger = logging.getLogger(__name__)


def patched_send_ping(self):
    """
    修复版 send_ping 方法
    
    改进:
    1. 在发送前检查 ws.keep_running 状态
    2. 检查 ws 对象是否存在且未关闭
    3. 捕获异常防止线程崩溃
    """
    while not self.stop_event.wait(50):
        # 检查1: keep_running标志
        if not self.ws.keep_running:
            break
        
        try:
            # 检查2: ws对象存在且未关闭
            if self.ws and hasattr(self.ws, 'sock') and self.ws.sock:
                logging.debug("Websocket sending ping")
                self.ws.send(json.dumps({"method": "ping"}))
            else:
                logging.debug("Websocket not ready for ping, skipping")
                break
                
        except Exception as e:
            # 捕获所有异常，防止线程崩溃
            logger.warning(f"Websocket ping发送失败: {e}")
            # 连接已断开，退出循环
            break
    
    logging.debug("Websocket ping sender stopped")


def apply_websocket_patch():
    """
    应用 Monkey Patch
    
    使用方法:
        from utils.websocket_patch import apply_websocket_patch
        apply_websocket_patch()
    """
    # 保存原始方法（用于调试）
    original_send_ping = WebsocketManager.send_ping
    
    # 替换为修复版方法
    WebsocketManager.send_ping = patched_send_ping
    
    logger.info("✅ WebSocket Monkey Patch 已应用: send_ping 方法已修复")
    logger.debug(f"原始方法: {original_send_ping}")
    logger.debug(f"修复方法: {patched_send_ping}")


# 自动应用补丁（当模块被导入时）
apply_websocket_patch()
