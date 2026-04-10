#!/usr/bin/env python3
"""
模板加载器 — 供其他模块直接使用已保存的模板配置

用法:
    from src.core.capabilities.template_loader import TemplateLoader

    loader = TemplateLoader()
    config = loader.load()

    # 获取模板路径
    capture_path = loader.get_template_path("capture_mode")
    battle_path = loader.get_template_path("battle_mode")

    # 根据相对坐标，在任何尺寸的截图上计算绝对区域
    region = loader.get_region("capture_mode", screen_width=1280, screen_height=720)
    # 返回 (x, y, w, h) 绝对坐标
"""

import os
import json
from typing import Optional, Tuple
from src.logger import get_logger

# 模板配置路径（基于当前文件的绝对路径）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(_PROJECT_ROOT, "data", "templates")
CONFIG_PATH = os.path.join(TEMPLATE_DIR, "templates_config.json")


class TemplateLoader:
    """模板配置加载器，使用相对坐标适配不同分辨率"""

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.logger = get_logger()
        self._config: dict = {}

    def load(self) -> dict:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            self.logger.warning(f"模板配置不存在: {self.config_path}")
            self.logger.info("请先运行 template_captor 截取模板")
            return {}

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = json.load(f)

        self.logger.info(f"加载模板配置: {self.config_path}")
        for name, tpl in self._config.get("templates", {}).items():
            self.logger.info(
                f"  {name}: rel=({tpl['rel_x']}, {tpl['rel_y']}, "
                f"{tpl['rel_w']}, {tpl['rel_h']})"
            )
        return self._config

    def get_template(self, name: str) -> Optional[dict]:
        """获取指定模板的配置数据"""
        if not self._config:
            self.load()
        return self._config.get("templates", {}).get(name)

    def get_template_path(self, name: str) -> Optional[str]:
        """获取模板图片路径"""
        tpl = self.get_template(name)
        if tpl:
            return tpl.get("template_path")
        return None

    def get_region(
        self, name: str, screen_width: int, screen_height: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        根据相对坐标 + 当前屏幕尺寸，计算绝对区域

        Args:
            name: 模板名称 (capture_mode / battle_mode)
            screen_width: 当前游戏窗口宽度
            screen_height: 当前游戏窗口高度

        Returns:
            (x, y, w, h) 绝对坐标，或 None
        """
        tpl = self.get_template(name)
        if not tpl:
            return None

        x = int(tpl["rel_x"] * screen_width)
        y = int(tpl["rel_y"] * screen_height)
        w = int(tpl["rel_w"] * screen_width)
        h = int(tpl["rel_h"] * screen_height)
        return (x, y, w, h)

    def has_template(self, name: str) -> bool:
        """检查模板是否存在"""
        if not self._config:
            self.load()
        return name in self._config.get("templates", {})
