#!/usr/bin/env python3
"""
瞄准配置管理模块

提供瞄准策略的各种配置选项，包括：
- 瞄准持续时间
- 移动速度参数
- P控制参数
- 瞄准容忍度
- 算法开关等
"""

from dataclasses import dataclass
from typing import Optional
import json
from pathlib import Path

from src.logger import get_logger


@dataclass
class AimConfig:
    """瞄准配置类。

    所有关于瞄准行为的参数都可以在这里配置。
    """

    # === 基础瞄准参数 ===
    aim_duration: float = 3.0  # 持续瞄准时间（秒）
    aim_tolerance: int = 40     # 目标中心与准心最大允许偏差（像素）
    mouse_to_view_ratio: float = 1.0  # 鼠标移动与视角移动比例

    # === 持续瞄准（Step 3）参数 ===
    check_interval: float = 0.050    # 检查间隔（秒）
    max_move_per_check: int = 30    # 每次检查最大移动像素数
    p_factor: float = 0.4           # P控制因子（0-1），越小越平滑

    # === 快速定位（Step 1）参数 ===
    initial_move_threshold: int = 10  # 初始移动的最小阈值
    initial_wait_min: float = 0.05   # 初始等待最小时间（秒）
    initial_wait_max: float = 0.10   # 初始等待最大时间（秒）

    # === 微调（Step 4）参数 ===
    fine_tune_enabled: bool = True   # 是否启用微调
    fine_tune_duration: int = 500    # 微调时长（毫秒）
    micro_move_range: int = 5        # 微调移动范围（像素）

    # === 算法开关 ===
    use_compensation: bool = True    # 是否启用距离补偿
    use_prediction: bool = True      # 是否启用动量预测
    use_smoothing: bool = True       # 是否启用平滑滤波

    # === 算法参数 ===
    smoothing_alpha: float = 0.3     # 平滑滤波系数（0-1）
    flight_time: float = 0.5         # 精灵球预估飞行时间（秒）

    # === 遮挡处理参数 ===
    handle_occlusion: bool = True    # 是否启用遮挡处理
    max_occlusion_attempts: int = 3  # 最大遮挡尝试次数
    camera_up_offset: int = 150      # 抬高摄像头的像素距离
    occlusion_wait_time: float = 0.2 # 抬高视角后的等待时间（秒）

    # === 日志和调试 ===
    debug: bool = False              # 是否输出调试日志
    log_move_threshold: int = 1      # 记录移动的最小阈值

    def __post_init__(self):
        """验证参数范围。"""
        if not 0.0 <= self.p_factor <= 1.0:
            raise ValueError("p_factor 必须在 0 到 1 之间")
        if not 0.0 <= self.smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha 必须在 0 到 1 之间")
        if self.aim_duration <= 0:
            raise ValueError("aim_duration 必须大于 0")
        if self.check_interval <= 0:
            raise ValueError("check_interval 必须大于 0")

    @classmethod
    def from_file(cls, config_path: Optional[str] = None) -> "AimConfig":
        """从配置文件加载配置。

        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径

        Returns:
            AimConfig 实例
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "aim_config.json"

        config_file = Path(config_path)

        # 如果文件不存在，返回默认配置
        if not config_file.exists():
            logger = get_logger()
            logger.info(f"配置文件不存在: {config_file}，使用默认配置")
            return cls()

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 创建配置实例
            config = cls(**data)
            logger = get_logger()
            logger.info(f"已加载配置文件: {config_file}")
            return config

        except Exception as e:
            logger = get_logger()
            logger.warning(f"加载配置文件失败 ({config_file}): {e}，使用默认配置")
            return cls()

    def save_to_file(self, config_path: Optional[str] = None) -> bool:
        """保存配置到文件。

        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径

        Returns:
            是否保存成功
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "aim_config.json"

        config_file = Path(config_path)

        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 转换为字典并保存
            data = {
                "aim_duration": self.aim_duration,
                "aim_tolerance": self.aim_tolerance,
                "mouse_to_view_ratio": self.mouse_to_view_ratio,
                "check_interval": self.check_interval,
                "max_move_per_check": self.max_move_per_check,
                "p_factor": self.p_factor,
                "initial_move_threshold": self.initial_move_threshold,
                "initial_wait_min": self.initial_wait_min,
                "initial_wait_max": self.initial_wait_max,
                "fine_tune_enabled": self.fine_tune_enabled,
                "fine_tune_duration": self.fine_tune_duration,
                "micro_move_range": self.micro_move_range,
                "use_compensation": self.use_compensation,
                "use_prediction": self.use_prediction,
                "use_smoothing": self.use_smoothing,
                "smoothing_alpha": self.smoothing_alpha,
                "flight_time": self.flight_time,
                "debug": self.debug,
                "log_move_threshold": self.log_move_threshold,
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger = get_logger()
            logger.info(f"配置已保存到: {config_file}")
            return True

        except Exception as e:
            logger = get_logger()
            logger.info(f"保存配置文件失败: {e}")
            return False

    def apply_to_aim_and_throw(self, aim_throw_instance) -> None:
        """将配置应用到 AimAndThrow 实例。

        Args:
            aim_throw_instance: AimAndThrow 实例
        """
        # 基础参数
        aim_throw_instance.AIM_DURATION = self.aim_duration
        aim_throw_instance.AIM_TOLERANCE = self.aim_tolerance
        aim_throw_instance.MOUSE_TO_VIEW_RATIO = self.mouse_to_view_ratio

        # 算法开关
        aim_throw_instance._use_compensation = self.use_compensation
        aim_throw_instance._use_prediction = self.use_prediction
        aim_throw_instance._use_smoothing = self.use_smoothing

        # 算法参数
        aim_throw_instance._flight_time = self.flight_time
        aim_throw_instance._smooth_filter.alpha = self.smoothing_alpha

        # 调试标志
        aim_throw_instance.debug = self.debug

    def to_dict(self) -> dict:
        """转换为字典格式，便于打印和调试。"""
        return {
            "瞄准时长(秒)": self.aim_duration,
            "瞄准容忍度(像素)": self.aim_tolerance,
            "鼠标视角比例": self.mouse_to_view_ratio,
            "检查间隔(秒)": self.check_interval,
            "最大单次移动(像素)": self.max_move_per_check,
            "P控制因子": self.p_factor,
            "初始移动阈值": self.initial_move_threshold,
            "初始等待最小(秒)": self.initial_wait_min,
            "初始等待最大(秒)": self.initial_wait_max,
            "微调时长(毫秒)": self.fine_tune_duration,
            "微调范围(像素)": self.micro_move_range,
            "启用距离补偿": self.use_compensation,
            "启用动量预测": self.use_prediction,
            "启用平滑滤波": self.use_smoothing,
            "平滑系数": self.smoothing_alpha,
            "预估飞行时间(秒)": self.flight_time,
            "调试模式": self.debug,
            "日志移动阈值": self.log_move_threshold,
        }


# 创建默认配置实例
default_config = AimConfig()


def create_default_config_file() -> bool:
    """创建默认配置文件。

    Returns:
        是否创建成功
    """
    return default_config.save_to_file()


if __name__ == "__main__":
    # 测试配置系统
    print("创建默认配置文件...")
    create_default_config_file()

    # 加载并打印配置
    config = AimConfig.from_file()
    print("\n当前配置:")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")