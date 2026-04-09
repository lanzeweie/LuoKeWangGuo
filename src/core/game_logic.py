#!/usr/bin/env python3
"""
游戏逻辑模块
计算移动路径、投掷参数等
"""

import math
from typing import Optional, Tuple
from src.core.detection import DetectionResult
from src.logger import get_logger


class GameLogic:
    """游戏逻辑处理器"""

    def __init__(self, frame_width: int = 1280, frame_height: int = 720, debug: bool = False):
        """
        初始化游戏逻辑

        Args:
            frame_width: 画面宽度
            frame_height: 画面高度
            debug: 是否启用调试模式
        """
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.debug = debug
        self.logger = get_logger(debug=debug)

        # 投掷参数
        self.throw_distance_threshold = 300  # 投掷距离阈值（像素）
        self.throw_angle_offset = 0  # 投掷角度偏移（度）

    def calculate_relative_position(
        self,
        player_center: Tuple[int, int],
        target_center: Tuple[int, int]
    ) -> Tuple[int, int, float]:
        """
        计算目标相对于玩家的位置

        Args:
            player_center: 玩家中心点 (x, y)
            target_center: 目标中心点 (x, y)

        Returns:
            (dx, dy, distance) - 相对坐标和距离
        """
        dx = target_center[0] - player_center[0]
        dy = target_center[1] - player_center[1]
        distance = math.sqrt(dx ** 2 + dy ** 2)

        if self.debug:
            self.logger.debug_msg(f"相对位置: dx={dx}, dy={dy}, 距离={distance:.1f}")

        return dx, dy, distance

    def should_throw(
        self,
        player_pos: Optional[Tuple[int, int]],
        target_pos: Tuple[int, int]
    ) -> bool:
        """
        判断是否应该投掷

        Args:
            player_pos: 玩家位置（可选，None表示使用画面中心）
            target_pos: 目标位置

        Returns:
            True if should throw
        """
        if player_pos is None:
            # Use screen center as player position
            player_pos = (self.frame_width // 2, self.frame_height // 2)

        dx, dy, distance = self.calculate_relative_position(player_pos, target_pos)

        # Check if target is within throw distance
        result = distance <= self.throw_distance_threshold

        if self.debug:
            self.logger.debug_msg(f"投掷判断: 距离={distance:.1f}, 阈值={self.throw_distance_threshold}, 结果={result}")

        return result

    def calculate_throw_parameters(
        self,
        player_pos: Tuple[int, int],
        target_pos: Tuple[int, int]
    ) -> Tuple[float, float]:
        """
        计算投掷参数（角度、力度）

        Args:
            player_pos: 玩家位置
            target_pos: 目标位置

        Returns:
            (angle, power) - 投掷角度（度）和力度（0-1）
        """
        dx, dy, distance = self.calculate_relative_position(player_pos, target_pos)

        # Calculate angle (convert to degrees)
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        # Normalize angle to 0-360
        angle_deg = (angle_deg + 360) % 360

        # Calculate power based on distance (linear mapping)
        max_distance = self.throw_distance_threshold * 2
        power = min(1.0, distance / max_distance)

        if self.debug:
            self.logger.debug_msg(f"投掷参数: 角度={angle_deg:.1f}°, 力度={power:.3f}")

        return angle_deg, power

    def get_movement_direction(
        self,
        player_pos: Optional[Tuple[int, int]],
        target_pos: Tuple[int, int]
    ) -> Optional[str]:
        """
        获取移动方向

        Args:
            player_pos: 玩家位置（可选）
            target_pos: 目标位置

        Returns:
            移动方向 ('w', 'a', 's', 'd') or None
        """
        if player_pos is None:
            player_pos = (self.frame_width // 2, self.frame_height // 2)

        dx, dy, distance = self.calculate_relative_position(player_pos, target_pos)

        # If already in throw range, no need to move
        if distance <= self.throw_distance_threshold:
            if self.debug:
                self.logger.debug_msg("目标在投掷范围内，无需移动")
            return None

        # Determine primary movement direction
        if abs(dx) > abs(dy):
            # Horizontal movement is dominant
            direction = 'd' if dx > 0 else 'a'
        else:
            # Vertical movement is dominant
            direction = 's' if dy > 0 else 'w'

        if self.debug:
            self.logger.debug_msg(f"移动方向: {direction} (dx={dx}, dy={dy})")

        return direction

    def calculate_movement_duration(self, distance: float) -> float:
        """
        根据距离计算移动持续时间

        Args:
            distance: 距离（像素）

        Returns:
            移动时间（秒）
        """
        # 简单策略：距离越远，移动时间越长
        base_time = 0.2
        scale = 0.001  # 每像素增加的时间
        duration = base_time + distance * scale
        duration = min(duration, 1.0)  # 最大1秒

        if self.debug:
            self.logger.debug_msg(f"移动时间: {duration:.3f}s (距离={distance:.1f})")

        return duration

    def get_optimal_ball_type(self, distance: float, target_area: int) -> str:
        """
        根据距离和目标大小选择最佳捕捉球

        Args:
            distance: 距离（像素）
            target_area: 目标面积（像素）

        Returns:
            球类型 ('normal' 或 'super')
        """
        # 简单策略：远距离或小目标使用超级球
        if distance > 250 or target_area < 8000:
            return 'super'
        else:
            return 'normal'


def test_game_logic():
    """测试游戏逻辑"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("游戏逻辑模块测试")
    logger.info("=" * 50)

    from src.core.detection import DetectionResult

    # 测试1: 初始化
    logger.info("\n[测试1] 初始化游戏逻辑...")
    logic = GameLogic(1280, 720, debug=True)

    # 测试2: 计算相对位置
    logger.info("\n[测试2] 计算相对位置...")
    player = (640, 360)
    target_center = (800, 400)
    dx, dy, dist = logic.calculate_relative_position(player, target_center)
    logger.info(f"相对坐标: dx={dx}, dy={dy}, 距离={dist:.1f}")

    # 测试3: 判断是否应该投掷
    logger.info("\n[测试3] 判断是否应该投掷...")
    should = logic.should_throw(player, target_center)
    logger.info(f"应该投掷: {should}")

    # 测试4: 计算投掷参数
    logger.info("\n[测试4] 计算投掷参数...")
    angle, power = logic.calculate_throw_parameters(player, target_center)
    logger.info(f"投掷角度: {angle:.1f}°, 力度: {power:.3f}")

    # 测试5: 获取移动方向
    logger.info("\n[测试5] 获取移动方向...")
    far_target = (1000, 500)
    direction = logic.get_movement_direction(player, far_target)
    logger.info(f"移动方向: {direction}")

    # 测试6: 计算移动时间
    logger.info("\n[测试6] 计算移动时间...")
    duration = logic.calculate_movement_duration(300)
    logger.info(f"移动时间: {duration:.3f}s")

    # 测试7: 选择最佳球类型
    logger.info("\n[测试7] 选择最佳球类型...")
    ball_type = logic.get_optimal_ball_type(200, 10000)
    logger.info(f"推荐球类型: {ball_type}")

    logger.success("\n✓ 游戏逻辑测试完成")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_game_logic()
