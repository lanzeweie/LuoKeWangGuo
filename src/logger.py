#!/usr/bin/env python3
"""
日志模块
简单文本日志输出
"""

from datetime import datetime
from typing import Optional


class Logger:
    """简单日志类"""

    def __init__(self, debug: bool = False):
        self.debug = debug

    def _print(self, message: str, emoji: str):
        """通用打印方法"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {emoji} {message}", flush=True)

    def info(self, message: str):
        """信息日志"""
        self._print(message, "ℹ️")

    def success(self, message: str):
        """成功日志"""
        self._print(message, "✓")

    def warning(self, message: str):
        """警告日志"""
        self._print(message, "⚠️")

    def error(self, message: str):
        """错误日志"""
        self._print(message, "✗")

    def debug_msg(self, message: str):
        """调试日志（仅在 debug 模式下输出）"""
        if self.debug:
            self._print(message, "🔍")


# 全局日志实例
_logger: Optional[Logger] = None


def get_logger(debug: bool = False) -> Optional[Logger]:
    """获取全局日志实例"""
    global _logger
    if _logger is None:
        _logger = Logger(debug=debug)
    return _logger


def set_logger(logger: Logger):
    """设置全局日志实例"""
    global _logger
    _logger = logger
