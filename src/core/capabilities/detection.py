#!/usr/bin/env python3
"""
目标检测模块
加载YOLO模型并执行实时目标检测
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from ultralytics import YOLO
from src.logger import get_logger


class DetectionResult:
    """检测结果数据类"""

    def __init__(self, x1: int, y1: int, x2: int, y2: int, confidence: float, class_id: int):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence
        self.class_id = class_id

    @property
    def center(self) -> Tuple[int, int]:
        """目标中心点"""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    @property
    def width(self) -> int:
        """目标宽度"""
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        """目标高度"""
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        """目标面积"""
        return self.width * self.height


class ObjectDetector:
    """目标检测器"""

    def __init__(self, model_path: str, device: str = "cpu",
                 confidence_threshold: float = 0.5, iou_threshold: float = 0.7, debug: bool = False):
        """
        初始化目标检测器

        Args:
            model_path: YOLO模型路径 (.pt文件)
            device: 推理设备 ('cpu' 或 'cuda')
            confidence_threshold: 置信度阈值
            iou_threshold: NMS IoU 阈值（默认 0.7，越高越严格合并重叠框）
            debug: 是否启用调试模式
        """
        self.model_path = model_path
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.model: Optional[YOLO] = None
        self.inference_times: List[float] = []
        self.max_history = 100

    def load_model(self) -> bool:
        """
        加载YOLO模型

        Returns:
            bool: 是否成功加载
        """
        try:
            self.logger.info(f"加载模型: {self.model_path}")
            self.logger.info(f"推理设备: {self.device}")

            self.model = YOLO(self.model_path)

            self.logger.success("模型加载成功")
            return True
        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            return False

    def detect(self, frame: np.ndarray, target_class: Optional[int] = None) -> List[DetectionResult]:
        """
        在帧上执行目标检测

        Args:
            frame: BGR格式的图像 (H, W, 3)
            target_class: 目标类别ID，None表示检测所有类别

        Returns:
            检测结果列表
        """
        if self.model is None:
            self.logger.error("模型未加载")
            return []

        if frame is None or frame.size == 0:
            self.logger.error("无效的输入帧")
            return []

        try:
            import time
            start_time = time.time()

            # 执行推理
            results = self.model(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                device=self.device,
                verbose=False
            )

            inference_time = (time.time() - start_time) * 1000  # ms
            self.inference_times.append(inference_time)

            # 保留最近的历史
            if len(self.inference_times) > self.max_history:
                self.inference_times.pop(0)

            # 调试输出
            if self.debug:
                self.logger.debug_msg(f"推理时间: {inference_time:.2f}ms")

            detections = []

            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    # 检查置信度
                    confidence = float(box.conf[0])
                    if confidence < self.confidence_threshold:
                        continue

                    # 检查类别
                    class_id = int(box.cls[0])
                    if target_class is not None and class_id != target_class:
                        continue

                    # 提取边界框
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                    detection = DetectionResult(x1, y1, x2, y2, confidence, class_id)
                    detections.append(detection)

            # 调试输出
            if self.debug and detections:
                self.logger.debug_msg(f"检测到 {len(detections)} 个目标")

            return detections

        except Exception as e:
            self.logger.error(f"检测失败: {e}")
            return []

    def draw_detections(self, frame: np.ndarray, detections: List[DetectionResult]) -> np.ndarray:
        """
        在帧上绘制检测框

        Args:
            frame: 原始帧
            detections: 检测结果列表

        Returns:
            绘制了检测框的帧
        """
        import cv2

        frame_with_boxes = frame.copy()

        for det in detections:
            # 绘制边界框
            cv2.rectangle(frame_with_boxes, (det.x1, det.y1), (det.x2, det.y2), (0, 255, 0), 2)

            # 绘制标签
            label = f"Class {det.class_id}: {det.confidence:.2f}"
            cv2.putText(
                frame_with_boxes,
                label,
                (det.x1, det.y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

        return frame_with_boxes

    def get_top_detection(self, detections: List[DetectionResult]) -> Optional[DetectionResult]:
        """
        获取置信度最高的检测结果

        Args:
            detections: 检测结果列表

        Returns:
            置信度最高的检测结果或None
        """
        if not detections:
            return None

        return max(detections, key=lambda d: d.confidence)

    def get_avg_inference_time(self) -> float:
        """
        获取平均推理时间

        Returns:
            float: 平均推理时间 (ms)
        """
        if not self.inference_times:
            return 0.0
        return sum(self.inference_times) / len(self.inference_times)

    def unload_model(self):
        """卸载模型，释放资源"""
        if self.model is not None:
            del self.model
            self.model = None
            self.logger.info("模型已卸载")


def test_detector():
    """测试目标检测器"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("目标检测模块测试")
    logger.info("=" * 50)

    import os

    # 检查模型文件是否存在
    model_path = "models/trained/luoke_pet.pt"
    if not os.path.exists(model_path):
        logger.error(f"模型文件不存在: {model_path}")
        logger.error("请先训练模型")
        return False

    # 测试1: 初始化检测器
    logger.info("\n[测试1] 初始化检测器...")
    detector = ObjectDetector(
        model_path=model_path,
        device="cpu",
        confidence_threshold=0.5,
        debug=True
    )

    # 测试2: 加载模型
    logger.info("\n[测试2] 加载模型...")
    if not detector.load_model():
        logger.error("模型加载失败")
        return False

    # 测试3: 在测试图像上运行检测
    logger.info("\n[测试3] 在测试图像上运行检测...")
    import cv2

    test_images = [
        "data/images/PixPin_2026-04-08_20-19-32.png",
        "data/images/PixPin_2026-04-08_20-20-15.png",
    ]

    successful_detections = 0
    total_images = 0

    for img_path in test_images:
        if not os.path.exists(img_path):
            logger.warning(f"测试图像不存在: {img_path}")
            continue

        total_images += 1
        frame = cv2.imread(img_path)

        if frame is None:
            logger.warning(f"无法读取图像: {img_path}")
            continue

        # 执行检测
        detections = detector.detect(frame, target_class=0)

        if detections:
            successful_detections += 1
            top_det = detector.get_top_detection(detections)
            logger.success(f"✓ {img_path}: 检测到 {len(detections)} 个目标")
            if top_det:
                logger.info(f"  置信度: {top_det.confidence:.3f}")
                logger.info(f"  位置: {top_det.center}")
        else:
            logger.warning(f"✗ {img_path}: 未检测到目标")

    # 测试4: 性能统计
    logger.info("\n[测试4] 性能统计...")
    avg_time = detector.get_avg_inference_time()
    logger.info(f"平均推理时间: {avg_time:.2f}ms")

    if avg_time < 50:
        logger.success("✓ 推理速度达标 (<50ms)")
    else:
        logger.warning(f"⚠ 推理速度较慢 (目标<50ms，实际{avg_time:.2f}ms)")

    # 测试5: 检测成功率
    logger.info("\n[测试5] 检测准确率...")
    if total_images > 0:
        accuracy = successful_detections / total_images * 100
        logger.info(f"检测成功率: {accuracy:.1f}%")

        if accuracy >= 90:
            logger.success("✓ 检测准确率达标 (>=90%)")
        else:
            logger.warning(f"⚠ 检测准确率未达标 (目标>=90%，实际{accuracy:.1f}%)")

    detector.unload_model()

    logger.success("\n✓ 目标检测测试完成")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_detector()
