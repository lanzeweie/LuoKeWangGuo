#!/usr/bin/env python3
"""
检测覆盖层单元测试
"""

import numpy as np
import pytest

from src.core.capabilities.detection_overlay import (
    DetectionOverlay,
    TrackedTarget,
    calc_iou,
)


# ── Mock ObjectDetector ──


class MockDetector:
    """Mock YOLO 检测器"""

    def __init__(self):
        self.call_count = 0

    def detect(self):
        self.call_count += 1
        return []


# ── 测试 calc_iou ──


class TestCalcIou:
    """IoU 计算测试"""

    def test_no_overlap(self):
        """无重叠"""
        box1 = (0, 0, 10, 10)
        box2 = (20, 20, 30, 30)
        assert calc_iou(box1, box2) == 0.0

    def test_full_overlap(self):
        """完全重叠"""
        box1 = (0, 0, 10, 10)
        box2 = (0, 0, 10, 10)
        assert calc_iou(box1, box2) == 1.0

    def test_partial_overlap(self):
        """部分重叠"""
        box1 = (0, 0, 10, 10)
        box2 = (5, 5, 15, 15)
        # intersection = 5*5 = 25
        # area1 = 100, area2 = 100
        # union = 175
        # iou = 25/175 ≈ 0.143
        assert 0.14 < calc_iou(box1, box2) < 0.15

    def test_single_point(self):
        """单点框"""
        box1 = (0, 0, 1, 1)
        box2 = (5, 5, 6, 6)
        assert calc_iou(box1, box2) == 0.0


# ── 测试 DetectionOverlay ──


class TestDetectionOverlay:
    """检测覆盖层测试"""

    def test_init(self):
        """初始化"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
        )

        assert overlay.detect_interval == 3
        assert overlay.lerp_alpha == 0.3
        assert overlay.confirm_frames == 3
        assert overlay.lost_tolerance == 5
        assert overlay.iou_threshold == 0.3
        assert overlay.draw_boxes is True
        assert overlay._frame_count == 0
        assert overlay._next_track_id == 1

    def test_empty_frame_no_crash(self):
        """空帧输入不崩溃"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        targets = overlay.update(frame)

        assert isinstance(targets, list)

    def test_render_no_crash(self):
        """渲染不崩溃"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        output = overlay.render(frame, [])

        assert output.shape == frame.shape

    def test_render_no_draw_when_disabled(self):
        """draw_boxes=False 时不绘制"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
            draw_boxes=False,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        output = overlay.render(frame, [])

        # 应该返回拷贝
        assert output.shape == frame.shape
        assert output is not frame

    def test_reset(self):
        """重置"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
        )

        # 先创建一些目标，使 _next_track_id 递增
        overlay._frame_count = 100
        overlay._next_track_id = 5  # 假设之前创建了 4 个目标
        overlay._targets = [
            TrackedTarget(
                track_id=1,
                state="active",
                bbox=(10, 10, 50, 50),
                raw_bbox=(10, 10, 50, 50),
                prev_center=(30, 30),
                last_center=(30, 30),
                confidence=0.9,
                class_id=0,
            )
        ]

        overlay.reset()

        assert overlay._frame_count == 0
        assert overlay._targets == []
        # Track ID 应该保持不变（继续递增）
        assert overlay._next_track_id == 5

    def test_is_detect_frame(self):
        """检测帧判断"""
        mock_detector = MockDetector()
        overlay = DetectionOverlay(
            detector=mock_detector,
            screen_width=1280,
            screen_height=720,
            detect_interval=3,
        )

        for i in range(6):
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            # 首先调用 update 来更新 frame_count
            overlay.update(frame)

            if (i + 1) % 3 == 0:
                assert overlay.is_detect_frame is True, f"Frame {i+1} should be detect frame"
            else:
                assert overlay.is_detect_frame is False, f"Frame {i+1} should not be detect frame"


# ── 测试 TrackedTarget ──


class TestTrackedTarget:
    """TrackedTarget 数据类测试"""

    def test_creation(self):
        """创建"""
        target = TrackedTarget(
            track_id=1,
            state="candidate",
            bbox=(10, 10, 50, 50),
            raw_bbox=(10, 10, 50, 50),
            prev_center=(30, 30),
            last_center=(30, 30),
            confirm_count=1,
            lost_count=0,
            confidence=0.9,
            class_id=0,
        )

        assert target.track_id == 1
        assert target.state == "candidate"
        assert target.confirm_count == 1
        assert target.lost_count == 0


# ── Fixtures ──


@pytest.fixture
def mock_detector():
    return MockDetector()


@pytest.fixture
def overlay(mock_detector):
    return DetectionOverlay(
        detector=mock_detector,
        screen_width=1280,
        screen_height=720,
    )


@pytest.fixture
def sample_frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)


# ── 运行测试 ──


if __name__ == "__main__":
    pytest.main([__file__, "-v"])