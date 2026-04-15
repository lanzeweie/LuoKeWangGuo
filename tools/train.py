#!/usr/bin/env python3
"""
YOLO模型训练脚本 - 已修正输出路径为项目本地目录
"""

import argparse
import os
from ultralytics import YOLO


def train_model(data_yaml, epochs=100, imgsz=1280, batch_size=16, name="luoke_pet", device='0'):
    """
    训练YOLO模型

    Args:
        data_yaml: 数据集配置文件路径
        epochs: 训练轮数
        imgsz: 输入图像尺寸
        batch_size: 批次大小
        name: 训练任务名称
        device: 训练设备 ('cpu' 或 '0' 使用GPU)
    """
    # 强制获取项目根目录下的 models 文件夹绝对路径
    # os.path.abspath(__file__) 获取当前脚本 train.py 的绝对路径
    # os.path.dirname 获取其所在目录 G:\Code\YOLO\LuoKeWangGuo
    current_project_root = os.path.dirname(os.path.abspath(__file__))
    output_project_path = os.path.join(current_project_root, 'models')

    print(f"开始训练 YOLOv8n 模型...")
    print(f"  数据集: {data_yaml}")
    print(f"  训练轮数: {epochs}")
    print(f"  图像尺寸: {imgsz}")
    print(f"  批次大小: {batch_size}")
    print(f"  任务名称: {name}")
    print(f"  保存路径: {output_project_path}/{name}")
    print(f"  训练设备: {'GPU' if device != 'cpu' else 'CPU'}")

    # 加载预训练模型
    model = YOLO('models/base/yolov8n.pt')

    # 训练
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        name=name,
        project=output_project_path,  # 关键修改：使用绝对路径强制输出到本项目 models 目录
        device=device,
        workers=4,     # 数据加载线程数
        patience=50,   # 早停耐心值
        save=True,     # 保存检查点
        exist_ok=True, # 如果目录存在则覆盖
    )

    print("\n✓ 训练完成!")
    print(f"  最佳模型: {output_project_path}/{name}/weights/best.pt")
    print(f"  最后模型: {output_project_path}/{name}/weights/last.pt")

    return results


def main():
    parser = argparse.ArgumentParser(description="训练YOLO模型")
    parser.add_argument("--data", default="data/dataset.yaml", help="数据集配置文件")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=1280, help="图像尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--name", default="luoke_pet", help="训练任务名称")
    parser.add_argument("--device", default="0", help="设备 (cpu 或 0，默认为 GPU)")

    args = parser.parse_args()

    train_model(
        data_yaml=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch_size=args.batch,
        name=args.name,
        device=args.device
    )

    # 修正打印提示的路径
    print("\n下一步:")
    print(f"  1. 查看训练结果: models/{args.name}/")
    print(f"  2. 测试模型: yolo predict model=models/{args.name}/weights/best.pt source=data/images/")
    print(f"  3. 使用模型: python -m src.main --model models/{args.name}/weights/best.pt")


if __name__ == "__main__":
    main()