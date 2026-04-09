#!/usr/bin/env python3
"""
YOLO模型训练脚本
"""

import argparse
from ultralytics import YOLO


def train_model(data_yaml, epochs=100, imgsz=640, batch_size=16, name="luoke_pet"):
    """
    训练YOLO模型

    Args:
        data_yaml: 数据集配置文件路径
        epochs: 训练轮数
        imgsz: 输入图像尺寸
        batch_size: 批次大小
        name: 训练任务名称
    """
    print(f"开始训练 YOLOv8n 模型...")
    print(f"  数据集: {data_yaml}")
    print(f"  训练轮数: {epochs}")
    print(f"  图像尺寸: {imgsz}")
    print(f"  批次大小: {batch_size}")
    print(f"  任务名称: {name}")

    # 加载预训练模型
    model = YOLO('yolov8n.pt')  # nano 模型（适合CPU）

    # 训练
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        name=name,
        device='cpu',  # 使用CPU训练（可根据需要改为 0 使用GPU）
        workers=4,     # 数据加载线程数
        patience=50,   # 早停耐心值
        save=True,     # 保存检查点
        exist_ok=True, # 如果目录存在则覆盖
    )

    print("\n✓ 训练完成!")
    print(f"  最佳模型: runs/detect/{name}/weights/best.pt")
    print(f"  最后模型: runs/detect/{name}/weights/last.pt")

    return results


def main():
    parser = argparse.ArgumentParser(description="训练YOLO模型")
    parser.add_argument("--data", default="data/dataset.yaml", help="数据集配置文件")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=640, help="图像尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--name", default="luoke_pet", help="训练任务名称")
    parser.add_argument("--device", default="cpu", help="设备 (cpu 或 0)")

    args = parser.parse_args()

    train_model(
        data_yaml=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch_size=args.batch,
        name=args.name
    )

    print("\n下一步:")
    print(f"  1. 查看训练结果: runs/detect/{args.name}/")
    print(f"  2. 测试模型: yolo predict model=models/trained/{args.name}.pt source=data/images/")
    print(f"  3. 使用模型: python -m src.main --model models/trained/{args.name}.pt")


if __name__ == "__main__":
    main()
