#!/usr/bin/env python3
"""
后台检测线程封装

在独立线程中完成 YOLO 检测 + CV 模式检测，避免 dxcam 并发冲突。
主线程通过 get_latest() 拉取结果，非阻塞。

设计要点：
1. 同一线程内完成 YOLO + CV 检测（避免 dxcam 并发冲突）
2. 线程安全的数据拉取接口（主线程按需调用）
3. 生命周期管理（start/stop）
"""

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable

import numpy as np

from src.core.capabilities.detection import DetectionResult
from src.core.capabilities.detection_overlay import TrackedTarget


@dataclass
class DetectionSnapshot:
    """某时刻的完整检测快照"""
    tracked: List[TrackedTarget] = field(default_factory=list)
    det_results: List[DetectionResult] = field(default_factory=list)
    capture_detected: bool = False
    conf_cap: float = 0.0
    battle_detected: bool = False
    seq: int = 0


class DetectionWorker:
    """
    后台检测线程封装。

    在独立线程中持续执行：
    1. dxcam 截图
    2. DetectionOverlay.update() — YOLO 跳帧跟踪
    3. CV 模式检测（同一线程，避免 dxcam 并发冲突）

    主线程通过 get_latest() 拉取最新快照，非阻塞。
    """

    def __init__(
        self,
        capture,  # ScreenCaptureWithRegion
        overlay_detector,  # DetectionOverlay
        capture_detector=None,  # CaptureModeDetector | None
        battle_detector=None,  # BattleModeDetector | None
        cv_interval: float = 0.1,  # CV 检测间隔（秒）
        capture_interval: float = 1.0 / 30,
    ):
        """
        Args:
            capture: ScreenCaptureWithRegion 实例
            overlay_detector: DetectionOverlay 实例
            capture_detector: CaptureModeDetector 实例（可选）
            battle_detector: BattleModeDetector 实例（可选）
            cv_interval: CV 检测最小间隔（秒），避免过于频繁调用
            capture_interval: 截图循环休眠时间
        """
        self._capture = capture
        self._overlay_detector = overlay_detector
        self._capture_detector = capture_detector
        self._battle_detector = battle_detector
        self._cv_interval = cv_interval
        self._capture_interval = capture_interval

        # 内部状态
        self._lock = threading.Lock()
        self._latest = DetectionSnapshot()
        self._seq = 0
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # CV 检测计时
        self._last_cv_time = 0.0

        # 保持上一次 CV 结果（避免 cv_interval 间隔期内被重置为 False）
        self._last_capture_detected = False
        self._last_conf_cap = 0.0
        self._last_battle_detected = False

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    @property
    def detect_seq(self) -> int:
        """当前检测序列号，主线程比较是否拿到新结果"""
        return self._seq

    def start(self):
        """启动后台检测线程"""
        if self._running:
            return
        self._stop = False
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self):
        """停止后台检测线程"""
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._running = False

    def _should_run_cv(self, now: float) -> bool:
        """判断是否应该运行 CV 检测（受 cv_interval 控制）"""
        return (now - self._last_cv_time) >= self._cv_interval

    def _worker_loop(self):
        """后台线程主循环"""
        while not self._stop:
            frame = self._capture.capture()
            if frame is None:
                time.sleep(self._capture_interval * 0.1)
                continue

            now = time.time()

            # ── 1. YOLO 检测（通过 overlay_detector.update，跳帧调度由内部处理） ──
            tracked = self._overlay_detector.update(frame)

            # 提取需要绘框的目标
            draw_targets = [t for t in tracked if t.state in ("active", "lost", "candidate")]
            det_results = []
            for t in draw_targets:
                x1, y1, x2, y2 = map(int, t.bbox)
                det = DetectionResult(x1, y1, x2, y2, t.confidence, t.class_id)
                det_results.append(det)

            # ── 2. CV 模式检测（同一线程，避免 dxcam 并发冲突） ──
            if self._capture_detector is not None and self._should_run_cv(now):
                cap_detected, conf_cap = self._capture_detector.is_capture_mode(frame)
                self._last_capture_detected = cap_detected
                self._last_conf_cap = conf_cap
                self._last_cv_time = now
            else:
                cap_detected = self._last_capture_detected
                conf_cap = self._last_conf_cap

            if self._battle_detector is not None and self._should_run_cv(now):
                batt_detected, _ = self._battle_detector.is_battle_mode(frame)
                self._last_battle_detected = batt_detected
            else:
                batt_detected = self._last_battle_detected

            # ── 3. 原子写入 ──
            with self._lock:
                self._latest = DetectionSnapshot(
                    tracked=tracked,
                    det_results=det_results,
                    capture_detected=cap_detected,
                    conf_cap=conf_cap,
                    battle_detected=batt_detected,
                    seq=self._seq + 1,
                )
                self._seq += 1

            # 低优先级休眠
            time.sleep(self._capture_interval * 0.1)

    def get_latest(self) -> DetectionSnapshot:
        """
        主线程调用，获取最新检测快照（非阻塞）。
        返回一个副本，主线程可以自由使用。
        """
        with self._lock:
            snapshot = DetectionSnapshot(
                tracked=list(self._latest.tracked),
                det_results=list(self._latest.det_results),
                capture_detected=self._latest.capture_detected,
                conf_cap=self._latest.conf_cap,
                battle_detected=self._latest.battle_detected,
                seq=self._latest.seq,
            )
        return snapshot
