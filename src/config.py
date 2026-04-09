#!/usr/bin/env python3
"""
配置管理模块
"""

import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """配置数据类"""
    # 模型配置
    model_path: str
    target_class: int = 0
    confidence_threshold: float = 0.5

    # 窗口配置
    process_name: str = "NRC-Win64-Shipping.exe"
    resolution: str = "1280x720"
    width: int = 1280
    height: int = 720

    # 性能配置
    fps: int = 60
    device: str = "cpu"

    # 功能开关
    debug: bool = False
    dry_run: bool = False

    def __post_init__(self):
        # 解析分辨率
        if "x" in self.resolution:
            w, h = self.resolution.split("x")
            self.width = int(w)
            self.height = int(h)


def parse_args() -> Config:
    """解析命令行参数并返回配置对象"""
    parser = argparse.ArgumentParser(description="洛克王国自动宠物捕捉脚本")

    # 模型相关
    parser.add_argument("--model", required=True, help="YOLO模型路径 (.pt文件)")
    parser.add_argument("--target-class", type=int, default=0, help="目标宠物类别ID")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")

    # 窗口相关
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--resolution", default="1280x720", help="游戏分辨率")

    # 性能相关
    parser.add_argument("--fps", type=int, default=60, help="帧率限制")
    parser.add_argument("--device", default="cpu", help="推理设备 (cpu 或 0)")

    # 功能开关
    parser.add_argument("--debug", action="store_true", help="调试模式（显示检测框）")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不执行实际操作）")

    args = parser.parse_args()

    return Config(
        model_path=args.model,
        target_class=args.target_class,
        confidence_threshold=args.confidence,
        process_name=args.process_name,
        resolution=args.resolution,
        fps=args.fps,
        device=args.device,
        debug=args.debug,
        dry_run=args.dry_run,
    )
