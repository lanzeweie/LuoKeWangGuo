#!/usr/bin/env python3
"""
状态机控制模块
管理捕捉流程的状态转换
"""

from enum import Enum
from typing import Optional, List
from src.core.detection import DetectionResult
from src.core.target_scoring import TargetScore
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
        max_distance_threshold: float = 50.0,
        near_threshold: float = 100.0,
        capture_threshold: float = 200.0,
        debug: bool = False,
    ):
        """
        初始化状态机

        Args:
            max_distance_threshold: 太远阈值 (bbox area)
            near_threshold: 靠近阈值 (bbox area)
            capture_threshold: 捕捉阈值 (bbox area)
            debug: 是否启用调试模式
        """
        self._max_distance_threshold = max_distance_threshold
        self._near_threshold = near_threshold
        self._capture_threshold = capture_threshold
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
            import time
            self.state_start_time = time.time()

    def update(self, detections: list) -> State:
        """
        更新状态机

        Args:
            detections: 当前检测到的目标列表

        Returns:
            新的当前状态
        """
        import time

        # 检查状态超时
        elapsed = time.time() - self.state_start_time
        if elapsed > self.timeout_threshold:
            self.logger.warning(f"状态超时 ({elapsed:.1f}s)，进入错误状态")
            self.transition(State.ERROR)
            return self.current_state

        # 状态处理
        if self.current_state == State.SEARCH:
            return self._handle_search(detections)
        elif self.current_state == State.VERIFY_STATE:
            return self._handle_verify(detections)
        elif self.current_state == State.MOVE_CLOSER:
            return self._handle_move_closer(detections)
        elif self.current_state == State.MOVE_TO_TARGET:
            return self._handle_move(detections)
        elif self.current_state == State.THROW:
            return self._handle_throw()
        elif self.current_state == State.WAIT:
            return self._handle_wait()
        elif self.current_state == State.COOLDOWN:
            return self._handle_cooldown()
        elif self.current_state == State.ERROR:
            return self._handle_error()

        return self.current_state

    def _handle_search(self, detections: list) -> State:
        """处理搜索状态"""
        if not detections:
            if self.debug:
                self.logger.debug_msg("未检测到目标，继续搜索...")
            return State.SEARCH

        # 找到目标，进入验证状态
        self.target = max(detections, key=lambda d: d.confidence)
        self.logger.success(f"找到目标! 置信度: {self.target.confidence:.3f}，开始验证")
        self.throw_count = 0  # 重置投掷次数
        self.transition(State.VERIFY_STATE)
        return self.current_state

    def _handle_verify(self, detections: list) -> State:
        """处理验证状态 — 等待多周期确认"""
        if not detections:
            self.logger.warning("验证时丢失目标，返回搜索状态")
            self.target = None
            self.transition(State.SEARCH)
            return self.current_state

        # 验证通过，检查距离
        self.target = max(detections, key=lambda d: d.confidence)
        cx, cy = self.target.center
        bbox_area = self.target.area

        if bbox_area < self._max_distance_threshold:
            # 太远，需要靠近
            self.logger.info(f"目标太远 (面积={bbox_area}px²)，需要靠近")
            self.transition(State.MOVE_CLOSER)
        elif bbox_area < self._near_threshold:
            # 中等距离，可以投掷
            self.logger.info(f"目标距离合适 (面积={bbox_area}px²)，准备投掷")
            self.transition(State.THROW)
        else:
            # 足够近，投掷
            self.logger.info(f"目标很近 (面积={bbox_area}px²)，准备投掷")
            self.transition(State.THROW)

        return self.current_state

    def _handle_move_closer(self, detections: list) -> State:
        """处理靠近状态 — WASD 小范围移动"""
        if not detections:
            self.logger.warning("靠近时丢失目标，返回搜索状态")
            self.target = None
            self.transition(State.SEARCH)
            return self.current_state

        self.target = max(detections, key=lambda d: d.confidence)
        bbox_area = self.target.area

        if bbox_area >= self._capture_threshold:
            self.logger.info(f"已足够近 (面积={bbox_area}px²)")
            self.transition(State.THROW)
        else:
            if self.debug:
                self.logger.debug_msg(f"靠近中... (当前面积={bbox_area}px²)")
            # TODO: 实际 WASD 移动逻辑

        return self.current_state

    def _handle_move(self, detections: list) -> State:
        """处理移动状态"""
        if not detections:
            self.logger.warning("移动时丢失目标，返回搜索状态")
            self.target = None
            self.transition(State.SEARCH)
            return self.current_state

        # 更新目标
        self.target = max(detections, key=lambda d: d.confidence)

        # 检查是否到达投掷范围
        from src.core.game_logic import GameLogic
        logic = GameLogic(1280, 720)
        player_pos = (640, 360)

        if logic.should_throw(player_pos, self.target.center):
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

        # 这里需要等待一段时间或检测投掷结果
        # 简化实现：等待固定时间后检查是否还需要继续
        import time
        time.sleep(1.5)  # 等待1.5秒

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

        import time
        time.sleep(2.0)  # 冷却2秒
        self.target = None
        self.transition(State.SEARCH)

        return self.current_state

    def _handle_error(self) -> State:
        """处理错误状态"""
        self.logger.error("进入错误状态，尝试恢复...")
        import time
        time.sleep(2.0)  # 等待2秒
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

    def get_state_info(self) -> dict:
        """
        获取当前状态信息

        Returns:
            状态信息字典
        """
        import time
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

    # 测试1: 初始化
    logger.info("\n[测试1] 初始化状态机...")
    sm = StateMachine(debug=True)
    logger.info(f"初始状态: {sm.current_state.value}")

    # 测试2: 搜索状态 - 无目标
    logger.info("\n[测试2] 搜索状态 (无目标)...")
    state = sm.update([])
    logger.info(f"当前状态: {state.value}")

    # 测试3: 搜索状态 - 找到目标
    logger.info("\n[测试3] 搜索状态 (找到目标)...")
    detections = [DetectionResult(800, 400, 850, 450, 0.92, 0)]
    state = sm.update(detections)
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
