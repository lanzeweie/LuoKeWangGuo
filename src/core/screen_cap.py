#!/usr/bin/env python3
"""
屏幕捕获模块
使用dxcam进行DX12屏幕捕获
"""

import numpy as np
from typing import Optional, Tuple
import time
from src.logger import get_logger


class ScreenCapture:
    """屏幕捕获器"""

    def __init__(self, fps: int = 60, debug: bool = False):
        """
        初始化屏幕捕获

        Args:
            fps: 目标帧率
            debug: 是否启用调试模式
        """
        self.fps = fps
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.camera = None
        self.last_frame_time = 0
        self.frame_interval = 1.0 / fps
        self.frame_count = 0
        self.start_time = 0.0

    def start(self, region: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        启动捕获

        Args:
            region: 可选的捕获区域 (left, top, right, bottom)
        """
        try:
            import dxcam

            self.logger.info("初始化屏幕捕获器...")

            # 创建相机实例
            self.camera = dxcam.create(
                output_color="BGR",
                output_idx=0,
            )

            if self.camera is None:
                raise RuntimeError("创建DXCamera实例失败")

            # 如果传入了 region，在 start 时配置
            start_kwargs = {"target_fps": self.fps, "video_mode": True}
            if region is not None:
                start_kwargs["region"] = region

            # 启动捕获（非阻塞模式）
            self.camera.start(**start_kwargs)

            self.logger.success(f"屏幕捕获已启动 (FPS={self.fps})")
            self.frame_count = 0
            self.start_time = time.time()
            self.last_frame_time = self.start_time

            return True

        except ImportError:
            self.logger.error("未找到dxcam。请安装: pip install dxcam")
            return False
        except Exception as e:
            self.logger.error(f"启动屏幕捕获失败: {e}")
            return False

    def capture(self) -> Optional[np.ndarray]:
        """
        捕获一帧

        Returns:
            BGR image array or None
        """
        if self.camera is None:
            self.logger.error("捕获器未启动")
            return None

        try:
            # Frame rate limiting
            current_time = time.time()
            elapsed = current_time - self.last_frame_time

            if elapsed < self.frame_interval:
                time.sleep(self.frame_interval - elapsed)

            # Capture frame
            frame = self.camera.grab()

            self.last_frame_time = time.time()
            self.frame_count += 1

            # 调试输出帧率
            if self.debug and self.frame_count % 30 == 0:
                elapsed_total = time.time() - self.start_time
                fps_actual = self.frame_count / elapsed_total if elapsed_total > 0 else 0
                self.logger.debug_msg(f"帧率: {fps_actual:.1f} FPS | 总帧数: {self.frame_count}")

            return frame

        except Exception as e:
            self.logger.error(f"捕获帧失败: {e}")
            return None

    def get_current_fps(self) -> float:
        """
        获取当前实际帧率

        Returns:
            float: FPS
        """
        if self.start_time == 0:
            return 0.0

        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0

        return self.frame_count / elapsed

    def stop(self):
        """停止捕获"""
        if self.camera:
            try:
                self.camera.stop()
                elapsed = time.time() - self.start_time
                fps_avg = self.frame_count / elapsed if elapsed > 0 else 0
                self.logger.info(f"捕获已停止 (总帧数: {self.frame_count}, 平均FPS: {fps_avg:.1f})")
            except Exception as e:
                self.logger.error(f"停止捕获失败: {e}")

    def __enter__(self):
        if self.start():
            return self
        else:
            return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def test_screen_capture():
    """测试屏幕捕获"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("屏幕捕获模块测试")
    logger.info("=" * 50)

    # 测试1: 初始化和启动
    logger.info("\n[测试1] 初始化屏幕捕获器...")
    cap = ScreenCapture(fps=30, debug=True)

    if not cap.start():
        logger.error("捕获器启动失败")
        return False

    # 测试2: 捕获10帧
    logger.info("\n[测试2] 捕获10帧测试...")
    frames_captured = 0
    capture_times = []

    for i in range(10):
        start = time.time()
        frame = cap.capture()
        elapsed = time.time() - start

        if frame is not None:
            frames_captured += 1
            capture_times.append(elapsed * 1000)  # 转换为毫秒
            logger.info(f"帧 {i+1}: 尺寸={frame.shape}, 捕获时间={elapsed*1000:.2f}ms")
        else:
            logger.warning(f"帧 {i+1}: 捕获失败")

        time.sleep(0.016)  # 模拟60FPS间隔

    cap.stop()

    # 测试3: 性能统计
    logger.info("\n[测试3] 性能统计...")
    if capture_times:
        avg_time = sum(capture_times) / len(capture_times)
        min_time = min(capture_times)
        max_time = max(capture_times)

        logger.info(f"平均捕获时间: {avg_time:.2f}ms")
        logger.info(f"最小捕获时间: {min_time:.2f}ms")
        logger.info(f"最大捕获时间: {max_time:.2f}ms")
        logger.info(f"成功帧数: {frames_captured}/10")

        # 验收标准检查
        if avg_time < 33:  # 目标30FPS，即33ms/帧
            logger.success("✓ 帧率达标 (<33ms/帧)")
        else:
            logger.warning(f"⚠ 帧率未达标 (目标<33ms，实际{avg_time:.2f}ms)")

        if frames_captured == 10:
            logger.success("✓ 帧捕获成功率100%")
        else:
            logger.warning(f"⚠ 帧捕获成功率 {frames_captured*10}%")
    else:
        logger.error("未捕获到任何有效帧")

    logger.success("\n✓ 屏幕捕获测试完成")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_screen_capture()
