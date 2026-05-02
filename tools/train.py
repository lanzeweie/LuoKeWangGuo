#!/usr/bin/env python3
"""
YOLO模型训练脚本
"""

import argparse
import os
import shutil
from ultralytics import YOLO

# 项目根目录: tools/ 的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, 'models')
BASE_MODELS_DIR = os.path.join(MODELS_DIR, 'base')


def train_model(data_yaml, base_model='yolov8n.pt', epochs=100, imgsz=1280, batch_size=16, name="luoke_pet", device='0'):
    """
    训练YOLO模型

    Args:
        data_yaml: 数据集配置文件路径
        base_model: 基础模型文件名 (位于 models/base/ 目录下)
        epochs: 训练轮数
        imgsz: 输入图像尺寸
        batch_size: 批次大小
        name: 训练任务名称
        device: 训练设备 ('cpu' 或 '0' 使用GPU)
    """
    base_model_path = os.path.join(BASE_MODELS_DIR, base_model)
    if not os.path.exists(base_model_path):
        print(f"错误: 基础模型不存在: {base_model_path}")
        print(f"可用模型: {os.listdir(BASE_MODELS_DIR)}")
        return None

    # AMP 检查会在当前工作目录下查找 yolo26n.pt，确保它存在且完整
    for model_file in os.listdir(BASE_MODELS_DIR):
        src = os.path.join(BASE_MODELS_DIR, model_file)
        dst = os.path.join(PROJECT_ROOT, model_file)
        # 不存在或大小不一致时复制
        if not os.path.exists(dst) or os.path.getsize(src) != os.path.getsize(dst):
            shutil.copy2(src, dst)

    print(f"开始训练 YOLO 模型...")
    print(f"  基础模型: {base_model_path}")
    print(f"  数据集: {data_yaml}")
    print(f"  训练轮数: {epochs}")
    print(f"  图像尺寸: {imgsz}")
    print(f"  批次大小: {batch_size}")
    print(f"  任务名称: {name}")
    print(f"  保存路径: {MODELS_DIR}/{name}")
    print(f"  训练设备: {'GPU' if device != 'cpu' else 'CPU'}")

    # 加载预训练模型
    model = YOLO(base_model_path)

    # 训练
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        name=name,
        project=MODELS_DIR,
        device=device,
        workers=4,
        patience=50,
        save=True,
        exist_ok=True,
        amp=True,   # 启用 AMP 自动混合精度
    )

    print("\n训练完成!")
    print(f"  最佳模型: {MODELS_DIR}/{name}/weights/best.pt")
    print(f"  最后模型: {MODELS_DIR}/{name}/weights/last.pt")

    return results


def main():
    available_bases = [f for f in os.listdir(BASE_MODELS_DIR) if f.endswith('.pt')]

    parser = argparse.ArgumentParser(description="训练YOLO模型")
    parser.add_argument("--data", default="data/dataset.yaml", help="数据集配置文件")
    parser.add_argument("--model", default="yolov8n.pt", choices=available_bases, help="基础模型 (默认: yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=1280, help="图像尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--name", default="luoke_pet", help="训练任务名称")
    parser.add_argument("--device", default="0", help="设备 (cpu 或 0，默认为 GPU)")

    args = parser.parse_args()

    train_model(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch_size=args.batch,
        name=args.name,
        device=args.device
    )

    print("\n下一步:")
    print(f"  1. 查看训练结果: models/{args.name}/")
    print(f"  2. 测试模型: yolo predict model=models/{args.name}/weights/best.pt source=data/images/")
    print(f"  3. 使用模型: python -m src.main --model models/{args.name}/weights/best.pt")


if __name__ == "__main__":
    main()