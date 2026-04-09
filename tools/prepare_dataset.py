#!/usr/bin/env python3
"""
数据集准备工具
创建YOLO训练所需的目录结构和配置文件
"""

import os
import yaml
from pathlib import Path


def create_dataset_yaml(dataset_dir, output_yaml="dataset/dataset.yaml"):
    """
    创建YOLO数据集配置文件

    Args:
        dataset_dir: 数据集根目录
        output_yaml: 输出配置文件路径
    """
    # 确保目录存在
    dataset_path = Path(dataset_dir)
    images_dir = dataset_path / "images"
    labels_dir = dataset_path / "labels"

    if not images_dir.exists():
        raise ValueError(f"图片目录不存在: {images_dir}")
    if not labels_dir.exists():
        raise ValueError(f"标注目录不存在: {labels_dir}")

    # 读取类别定义
    classes_file = dataset_path / "classes.txt"
    if not classes_file.exists():
        raise ValueError(f"类别定义文件不存在: {classes_file}")

    with open(classes_file, 'r', encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip()]

    print(f"检测到 {len(names)} 个类别: {', '.join(names)}")

    # 检查图片和标注文件是否匹配
    image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png"))
    label_files = list(labels_dir.glob("*.txt"))

    print(f"图片数量: {len(image_files)}")
    print(f"标注数量: {len(label_files)}")

    if len(image_files) != len(label_files):
        print("[WARN] 图片和标注数量不匹配!")
        # 找出缺失的标注
        image_names = {f.stem for f in image_files}
        label_names = {f.stem for f in label_files}
        missing_labels = image_names - label_names
        if missing_labels:
            print(f"缺少标注的图片: {len(missing_labels)}")
            for name in sorted(missing_labels)[:5]:  # 只显示前5个
                print(f"  - {name}")

    # 创建YOLO数据集配置
    dataset_config = {
        'path': str(dataset_path.resolve()),  # 数据集根目录
        'train': 'images',  # 训练集图片目录
        'val': 'images',    # 验证集图片目录（使用同一目录）
        'test': '',         # 测试集（可选）
        'names': {i: name for i, name in enumerate(names)},  # 类别映射
    }

    # 写入配置文件
    with open(output_yaml, 'w', encoding='utf-8') as f:
        yaml.dump(dataset_config, f, allow_unicode=True, default_flow_style=False)

    print(f"\n数据集配置已保存到: {output_yaml}")
    print("\n配置内容:")
    print(yaml.dump(dataset_config, allow_unicode=True, default_flow_style=False))


def verify_dataset(dataset_dir):
    """
    验证数据集完整性

    Args:
        dataset_dir: 数据集根目录
    """
    dataset_path = Path(dataset_dir)
    images_dir = dataset_path / "images"
    labels_dir = dataset_path / "labels"

    print("数据集验证:")
    print(f"  图片目录: {images_dir}")
    print(f"  标注目录: {labels_dir}")

    # 检查文件数量
    image_files = sorted(list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")))
    label_files = sorted(list(labels_dir.glob("*.txt")))

    print(f"\n统计:")
    print(f"  图片文件: {len(image_files)}")
    print(f"  标注文件: {len(label_files)}")

    # 检查匹配情况
    image_set = {f.stem for f in image_files}
    label_set = {f.stem for f in label_files}

    missing_labels = image_set - label_set
    missing_images = label_set - image_set

    if missing_labels:
        print(f"\n[WARN] 缺少标注的图片 ({len(missing_labels)}):")
        for name in sorted(missing_labels)[:10]:
            print(f"  - {name}")

    if missing_images:
        print(f"\n[WARN] 缺少图片的标注 ({len(missing_images)}):")
        for name in sorted(missing_images)[:10]:
            print(f"  - {name}")

    if not missing_labels and not missing_images:
        print("\n[OK] 数据集完整，图片和标注匹配!")

    # 随机检查几个标注文件
    if label_files:
        print("\n随机检查标注:")
        import random
        samples = random.sample(label_files, min(3, len(label_files)))
        for label_file in samples:
            with open(label_file, 'r') as f:
                lines = f.readlines()
                print(f"  {label_file.name}: {len(lines)} 个目标")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="准备YOLO数据集")
    parser.add_argument("--dataset", default="data", help="数据集目录")
    parser.add_argument("--output", default="data/dataset.yaml", help="输出配置文件")
    parser.add_argument("--verify", action="store_true", help="仅验证数据集")

    args = parser.parse_args()

    if args.verify:
        verify_dataset(args.dataset)
    else:
        create_dataset_yaml(args.dataset, args.output)
        print("\n下一步:")
        print("  1. 检查 data/dataset.yaml 配置是否正确")
        print("  2. 运行训练: python tools/train.py --data data/dataset.yaml")


if __name__ == "__main__":
    main()
