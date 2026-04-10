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
    border_offset: int = 0  # 边框裁剪偏移（像素）

    # 性能配置
    fps: int = 30  # 屏幕捕获帧率
    device: str = "cuda"

    # 功能开关
    debug: bool = False
    dry_run: bool = False

    # 目标验证
    detection_interval: float = 2.0        # 检测间隔（秒）
    verification_cycles: int = 3           # 需要连续检测次数
    max_distance_threshold: float = 50.0   # 太远阈值 (bbox area)
    near_threshold: float = 100.0          # 靠近阈值 (bbox area)
    capture_threshold: float = 200.0       # 捕捉阈值 (bbox area)
    screen_center_offset_x: int = 0        # 中心 x 偏移
    screen_center_offset_y: int = 0        # 中心 y 偏移

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
    parser.add_argument("--border-offset", type=int, default=0, help="边框裁剪偏移（像素），用于去除边框残留")

    # 性能相关
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备 (cuda 或 cpu)")

    # 功能开关
    parser.add_argument("--debug", action="store_true", help="调试模式（显示检测框）")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不执行实际操作）")

    # 目标验证
    parser.add_argument("--detection-interval", type=float, default=2.0, help="检测间隔秒数")
    parser.add_argument("--verification-cycles", type=int, default=3, help="需要连续检测次数")
    parser.add_argument("--max-distance", type=float, default=50.0, help="太远阈值 (bbox area)")
    parser.add_argument("--near-threshold", type=float, default=100.0, help="靠近阈值 (bbox area)")
    parser.add_argument("--capture-threshold", type=float, default=200.0, help="捕捉阈值 (bbox area)")
    parser.add_argument("--center-offset-x", type=int, default=0, help="屏幕中心 x 偏移")
    parser.add_argument("--center-offset-y", type=int, default=0, help="屏幕中心 y 偏移")

    args = parser.parse_args()

    return Config(
        model_path=args.model,
        target_class=args.target_class,
        confidence_threshold=args.confidence,
        process_name=args.process_name,
        resolution=args.resolution,
        border_offset=args.border_offset,
        fps=args.fps,
        device=args.device,
        debug=args.debug,
        dry_run=args.dry_run,
        detection_interval=args.detection_interval,
        verification_cycles=args.verification_cycles,
        max_distance_threshold=args.max_distance,
        near_threshold=args.near_threshold,
        capture_threshold=args.capture_threshold,
        screen_center_offset_x=args.center_offset_x,
        screen_center_offset_y=args.center_offset_y,
    )
