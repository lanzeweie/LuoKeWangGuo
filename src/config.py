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

    # 模式检测
    capture_mode_template: str = ""         # 精灵球模式模板路径
    battle_mode_template: str = ""          # 战斗模式模板路径
    mode_match_threshold: float = 0.8       # 模板匹配阈值
    mode_timeout: float = 3.0               # 模式检测超时（秒）

    # 检测覆盖层
    overlay_draw_boxes: bool = True           # 打框开关
    overlay_detect_interval: int = 3       # 跳帧间隔
    overlay_lerp_alpha: float = 0.3           # 插值平滑系数
    overlay_confirm_frames: int = 3           # 候选确认帧数
    overlay_lost_tolerance: int = 5          # 丢失容错帧数
    overlay_iou_threshold: float = 0.3       # IoU 匹配阈值
    overlay_max_predict_distance: float = 100.0  # Lost 最大预测距离

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

    # 模式检测
    parser.add_argument("--capture-template", default="", help="精灵球模式模板图路径")
    parser.add_argument("--battle-template", default="", help="战斗模式模板图路径")
    parser.add_argument("--match-threshold", type=float, default=0.8, help="模板匹配阈值")
    parser.add_argument("--mode-timeout", type=float, default=3.0, help="模式检测超时（秒）")

    # 检测覆盖层
    parser.add_argument("--overlay-draw-boxes", type=lambda x: x.lower() == "true", default=True, help="打框开关")
    parser.add_argument("--overlay-detect-interval", type=int, default=3, help="跳帧间隔")
    parser.add_argument("--overlay-lerp-alpha", type=float, default=0.3, help="插值平滑系数")
    parser.add_argument("--overlay-confirm-frames", type=int, default=3, help="候选确认帧数")
    parser.add_argument("--overlay-lost-tolerance", type=int, default=5, help="丢失容错帧数")
    parser.add_argument("--overlay-iou-threshold", type=float, default=0.3, help="IoU 匹配阈值")
    parser.add_argument("--overlay-max-predict-distance", type=float, default=100.0, help="Lost 最大预测距离")

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
        capture_mode_template=args.capture_template,
        battle_mode_template=args.battle_template,
        mode_match_threshold=args.match_threshold,
        mode_timeout=args.mode_timeout,
        overlay_draw_boxes=args.overlay_draw_boxes,
        overlay_detect_interval=args.overlay_detect_interval,
        overlay_lerp_alpha=args.overlay_lerp_alpha,
        overlay_confirm_frames=args.overlay_confirm_frames,
        overlay_lost_tolerance=args.overlay_lost_tolerance,
        overlay_iou_threshold=args.overlay_iou_threshold,
        overlay_max_predict_distance=args.overlay_max_predict_distance,
    )
