#!/usr/bin/env python3
"""
状态机控制模块
管理捕捉流程的状态转换
"""

import time
from enum import Enum
from typing import Optional, List
from src.core.detection import DetectionResult
from src.core.target_scoring import TargetScore
from src.core.target_verifier import TargetVerifier
from src.logger import get_logger


class State(Enum):
    """状态枚举"""
    SEARCH = "寻找目标"
    VERIFY_STATE = "验证目标"
    MOVE_CLOSER = "靠近目标"
    MOVE_TO_TARGET = "移动到目标"
    THROW = "投掷"
    WAIT = "等待结果"
    COOLDOWN = "冷却"
    ERROR = "错误"


class StateMachine:
    """状态机控制器"""

    def __init__(
        self,
        verifier: TargetVerifier,
        debug: bool = False,
    ):
        """
        初始化状态机

        Args:
            verifier: 目标验证器实例
            debug: 是否启用调试模式
        """
        self._verifier = verifier
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.current_state = State.SEARCH
        self.target: Optional[DetectionResult] = None
        self.verified_target: Optional[TargetScore] = None
        self.throw_count = 0
        self.max_throws = 3  # 每个目标最大投掷次数
        self.state_start_time: float = 0
        self.timeout_threshold: float = 10.0  # 状态超时阈值（秒）
        self.center_threshold: int = 40  # 目标在中心的阈值（像素）

    def transition(self, new_state: State):
        """
        状态转换

        Args:
            new_state: 新状态
        """
        if new_state != self.current_state:
            self.logger.info(f"状态转换: {self.current_state.value} → {new_state.value}")
            self.current_state = new_state
            self.state_start_time = time.time()

    def update(self, scored_detections: List[TargetScore]) -> State:
        """
        更新状态机

        Args:
            scored_detections: 已评分和排序的目标列表

        Returns:
            新的当前状态
        """
        # 检查状态超时
        elapsed = time.time() - self.state_start_time
        if elapsed > self.timeout_threshold:
            self.logger.warning(f"状态超时 ({elapsed:.1f}s)，进入错误状态")
            self.transition(State.ERROR)
            return self.current_state

        # 状态处理
        if self.current_state == State.SEARCH:
            return self._handle_search(scored_detections)
        elif self.current_state == State.VERIFY_STATE:
            return self._handle_verify(scored_detections)
        elif self.current_state == State.MOVE_CLOSER:
            return self._handle_move_closer(scored_detections)
        elif self.current_state == State.MOVE_TO_TARGET:
            return self._handle_move(scored_detections)
        elif self.current_state == State.THROW:
            return self._handle_throw()
        elif self.current_state == State.WAIT:
            return self._handle_wait()
        elif self.current_state == State.COOLDOWN:
            return self._handle_cooldown()
        elif self.current_state == State.ERROR:
            return self._handle_error()

        return self.current_state

    def _handle_search(self, scored: List[TargetScore]) -> State:
        """处理搜索状态"""
        if not scored:
            if self.debug:
                self.logger.debug_msg("未检测到目标，继续搜索...")
            return State.SEARCH

        # 找到目标，重置验证器并进入验证状态
        top = scored[0]
        self.target = top.detection
        self._verifier.reset()
        self.logger.success(f"找到目标! 置信度: {top.detection.confidence:.3f}，开始验证")
        self.throw_count = 0  # 重置投掷次数
        self.transition(State.VERIFY_STATE)
        return self.current_state

    def _handle_verify(self, scored: List[TargetScore]) -> State:
        """处理验证状态 — 由 TargetVerifier 驱动多周期确认"""
        verified, verified_target = self._verifier.process_cycle(scored)

        if verified:
            # 验证通过，根据距离状态决定下一步
            self.verified_target = verified_target
            self.target = verified_target.detection
            self.logger.success(
                f"验证通过 → 距离={verified_target.distance_state} "
                f"(面积={verified_target.bbox_area:.0f}px²)"
            )
            if verified_target.distance_state == "FAR":
                self.transition(State.MOVE_CLOSER)
            else:
                self.transition(State.THROW)
            return self.current_state

        # 验证未完成，继续等待
        if self.debug:
            self.logger.debug_msg(
                f"验证中 {self._verifier.verification_progress}/{self._verifier.required_cycles}"
            )
        return State.VERIFY_STATE

    def _handle_move_closer(self, scored: List[TargetScore]) -> State:
        """处理靠近状态 — WASD 小范围移动"""
        if not scored:
            self.logger.warning("靠近时丢失目标，返回搜索状态")
            self.target = None
            self._verifier.reset()
            self.transition(State.SEARCH)
            return self.current_state

        top = scored[0]
        self.target = top.detection

        if top.distance_state in ("MEDIUM", "CLOSE"):
            self.logger.info(f"已足够近 (面积={top.bbox_area:.0f}px²)")
            self.transition(State.THROW)
        else:
            if self.debug:
                self.logger.debug_msg(f"靠近中... (当前面积={top.bbox_area:.0f}px², FAR)")
            # TODO: 实际 WASD 移动逻辑

        return self.current_state

    def _handle_move(self, scored: List[TargetScore]) -> State:
        """处理移动状态"""
        if not scored:
            self.logger.warning("移动时丢失目标，返回搜索状态")
            self.target = None
            self._verifier.reset()
            self.transition(State.SEARCH)
            return self.current_state

        # 更新目标
        top = scored[0]
        self.target = top.detection

        if top.distance_state in ("MEDIUM", "CLOSE"):
            self.logger.info("已到达投掷范围")
            self.transition(State.THROW)
        else:
            if self.debug:
                self.logger.debug_msg("正在移动...")

        return self.current_state

    def _handle_throw(self) -> State:
        """处理投掷状态"""
        self.throw_count += 1
        self.logger.info(f"执行投掷 (第 {self.throw_count}/{self.max_throws} 次)")

        # 投掷后进入等待状态
        self.transition(State.WAIT)

        return self.current_state

    def _handle_wait(self) -> State:
        """处理等待状态"""
        if self.debug:
            self.logger.debug_msg("等待投掷结果...")

        elapsed = time.time() - self.state_start_time
        if elapsed < 1.5:
            return State.WAIT  # 未达标，继续等待

        # 检查是否达到最大投掷次数
        if self.throw_count >= self.max_throws:
            self.logger.warning(f"达到最大投掷次数 ({self.max_throws})")
            self.transition(State.COOLDOWN)
        else:
            self.logger.info("继续尝试捕捉")
            self.transition(State.THROW)

        return self.current_state

    def _handle_cooldown(self) -> State:
        """处理冷却状态"""
        if self.debug:
            self.logger.debug_msg("冷却中...")

        elapsed = time.time() - self.state_start_time
        if elapsed < 2.0:
            return State.COOLDOWN  # 未达标，继续冷却

        self.target = None
        self.transition(State.SEARCH)

        return self.current_state

    def _handle_error(self) -> State:
        """处理错误状态"""
        self.logger.error("进入错误状态，尝试恢复...")

        elapsed = time.time() - self.state_start_time
        if elapsed < 2.0:
            return State.ERROR  # 未达标，继续等待

        self.target = None
        self.transition(State.SEARCH)
        return self.current_state

    def get_target(self) -> Optional[DetectionResult]:
        """获取当前目标"""
        return self.target

    def reset(self):
        """重置状态机"""
        self.logger.info("重置状态机")
        self.current_state = State.SEARCH
        self.target = None
        self.verified_target = None
        self.throw_count = 0
        self._verifier.reset()

    def get_state_info(self) -> dict:
        """
        获取当前状态信息

        Returns:
            状态信息字典
        """
        elapsed = time.time() - self.state_start_time

        return {
            'current_state': self.current_state.value,
            'elapsed_time': f"{elapsed:.1f}s",
            'throw_count': self.throw_count,
            'has_target': self.target is not None
        }


def test_state_machine():
    """测试状态机"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("状态机模块测试")
    logger.info("=" * 50)

    from src.core.detection import DetectionResult
    from src.core.target_scoring import TargetScore

    # 测试1: 初始化
    logger.info("\n[测试1] 初始化状态机...")
    verifier = TargetVerifier(required_cycles=3, debug=True)
    sm = StateMachine(verifier=verifier, debug=True)
    logger.info(f"初始状态: {sm.current_state.value}")

    # 测试2: 搜索状态 - 无目标
    logger.info("\n[测试2] 搜索状态 (无目标)...")
    state = sm.update([])
    logger.info(f"当前状态: {state.value}")

    # 测试3: 搜索状态 - 找到目标
    logger.info("\n[测试3] 搜索状态 (找到目标)...")
    det = DetectionResult(800, 400, 850, 450, 0.92, 0)
    scored = [TargetScore(
        detection=det,
        distance_to_center=50.0,
        bbox_area=2500.0,
        distance_state="MEDIUM",
        priority_rank=1,
    )]
    state = sm.update(scored)
    logger.info(f"当前状态: {state.value}")
    logger.info(f"目标信息: {sm.target.center if sm.target else 'None'}")

    # 测试4: 获取状态信息
    logger.info("\n[测试4] 获取状态信息...")
    info = sm.get_state_info()
    for key, value in info.items():
        logger.info(f"  {key}: {value}")

    # 测试5: 重置状态机
    logger.info("\n[测试5] 重置状态机...")
    sm.reset()
    logger.info(f"重置后状态: {sm.current_state.value}")

    logger.success("\n✓ 状态机测试完成")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_state_machine()
