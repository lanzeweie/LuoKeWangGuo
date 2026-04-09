#!/usr/bin/env python3
"""
视频抽帧工具
从游戏录像中抽取帧用于标注
"""

import cv2
import os
import argparse
from pathlib import Path


def extract_frames(video_path, output_dir, interval=2, max_frames=100):
    """
    从视频中抽取帧

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        interval: 抽帧间隔（秒）
        max_frames: 最大帧数
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频文件: {video_path}")

    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = int(fps * interval)

    print(f"视频信息: {fps:.2f} FPS, 总帧数: {total_frames}")
    print(f"抽帧间隔: {interval}秒 ({frame_interval}帧)")

    frame_count = 0
    saved_count = 0

    while cap.isOpened() and saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        # 按间隔抽取
        if frame_count % frame_interval == 0:
            # 保存为jpg
            output_path = os.path.join(output_dir, f"frame_{saved_count:04d}.jpg")
            cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved_count += 1
            print(f"已保存: {output_path} ({saved_count}/{max_frames})")

        frame_count += 1

    cap.release()
    print(f"\n完成! 共保存 {saved_count} 帧到 {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="从视频中抽取帧")
    parser.add_argument("--video", required=True, help="输入视频文件路径")
    parser.add_argument("--output", default="data/images", help="输出目录")
    parser.add_argument("--interval", type=int, default=2, help="抽帧间隔（秒）")
    parser.add_argument("--max-frames", type=int, default=100, help="最大帧数")

    args = parser.parse_args()

    extract_frames(
        video_path=args.video,
        output_dir=args.output,
        interval=args.interval,
        max_frames=args.max_frames
    )


if __name__ == "__main__":
    main()
