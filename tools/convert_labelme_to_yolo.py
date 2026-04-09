#!/usr/bin/env python3
"""
LabelMe JSON to YOLO格式转换工具
将你的标注文件转换为YOLO训练格式
"""

import json
import os
from pathlib import Path


def convert_labelme_to_yolo(json_path, output_dir, image_width=1280, image_height=720):
    """
    转换单个LabelMe JSON文件到YOLO格式

    Args:
        json_path: LabelMe JSON文件路径
        output_dir: YOLO标签输出目录
        image_width: 图像宽度
        image_height: 图像高度
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 获取标注形状
    shapes = data.get('shapes', [])

    if not shapes:
        print(f"  ⚠ {json_path.name}: 无标注数据")
        return False

    # YOLO标签文件路径
    label_file = Path(output_dir) / f"{Path(json_path).stem}.txt"

    with open(label_file, 'w', encoding='utf-8') as f_out:
        for shape in shapes:
            label = shape.get('label', '')
            points = shape.get('points', [])
            shape_type = shape.get('shape_type', '')

            # 只处理矩形标注
            if shape_type != 'rectangle' or len(points) != 4:
                continue

            # 获取矩形坐标
            x1, y1 = points[0]
            x2, y2 = points[2]

            # 计算中心点、宽度、高度（归一化到0-1）
            x_center = (x1 + x2) / 2 / image_width
            y_center = (y1 + y2) / 2 / image_height
            width = abs(x2 - x1) / image_width
            height = abs(y2 - y1) / image_height

            # 写入YOLO格式: class_id x_center y_center width height
            # class_id 固定为 0（奇丽草）
            f_out.write(f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

    print(f"  ✓ {json_path.name} -> {label_file.name}")
    return True


def batch_convert(input_dir, output_dir, image_width=1280, image_height=720):
    """
    批量转换LabelMe JSON到YOLO格式

    Args:
        input_dir: 包含JSON文件的目录
        output_dir: YOLO标签输出目录
        image_width: 图像宽度
        image_height: 图像高度
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # 创建输出目录
    output_path.mkdir(parents=True, exist_ok=True)

    # 查找所有JSON文件
    json_files = list(input_path.glob("*.json"))

    if not json_files:
        print(f"✗ 未找到JSON文件: {input_dir}")
        return

    print(f"找到 {len(json_files)} 个JSON标注文件")
    print(f"输出目录: {output_dir}")
    print("-" * 50)

    success_count = 0
    for json_file in sorted(json_files):
        if convert_labelme_to_yolo(json_file, output_dir, image_width, image_height):
            success_count += 1

    print("-" * 50)
    print(f"✓ 转换完成: {success_count}/{len(json_files)} 个文件")

    # 复制图片到dataset/images
    image_output = Path("dataset/images")
    image_output.mkdir(parents=True, exist_ok=True)

    png_files = list(input_path.glob("*.png"))
    print(f"\n复制图片: {len(png_files)} 张")

    for png_file in sorted(png_files):
        dest = image_output / png_file.name
        if not dest.exists():
            dest.write_bytes(png_file.read_bytes())
            print(f"  ✓ {png_file.name}")

    print(f"✓ 所有图片已复制到: dataset/images/")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="LabelMe JSON to YOLO格式转换")
    parser.add_argument("--input", default=r"C:\Users\lanze\Downloads\奇丽花素材", help="输入目录（包含JSON和PNG）")
    parser.add_argument("--output", default="dataset/labels", help="YOLO标签输出目录")
    parser.add_argument("--width", type=int, default=1280, help="图像宽度")
    parser.add_argument("--height", type=int, default=720, help="图像高度")

    args = parser.parse_args()

    print("=" * 60)
    print("  LabelMe to YOLO 格式转换工具")
    print("=" * 60)
    print(f"  输入目录: {args.input}")
    print(f"  标签输出: {args.output}")
    print(f"  图像尺寸: {args.width}x{args.height}")
    print("=" * 60)
    print()

    batch_convert(args.input, args.output, args.width, args.height)

    print("\n" + "=" * 60)
    print("下一步:")
    print("  1. 检查 dataset/images/ 和 dataset/labels/")
    print("  2. 运行: python tools/prepare_dataset.py --dataset dataset --verify")
    print("  3. 运行: python tools/train.py --data dataset/dataset.yaml --epochs 100")
    print("=" * 60)


if __name__ == "__main__":
    main()
