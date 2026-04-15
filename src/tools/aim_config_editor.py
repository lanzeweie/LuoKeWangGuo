#!/usr/bin/env python3
"""
瞄准配置编辑器工具

提供交互式界面来编辑瞄准配置参数。
"""

from typing import Dict, Any
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.config.aim_config import AimConfig, default_config
from src.logger import get_logger, setup_logging

# 设置日志
setup_logging(debug=False)
logger = get_logger(debug=False)


def print_current_config(config: AimConfig) -> None:
    """打印当前配置。"""
    print("\n" + "="*60)
    print("当前瞄准配置:")
    print("="*60)

    # 分组显示配置
    groups = [
        ("基础瞄准参数", [
            ("aim_duration", "瞄准持续时间（秒）"),
            ("aim_tolerance", "瞄准容忍度（像素）"),
            ("mouse_to_view_ratio", "鼠标视角比例"),
        ]),
        ("微调速度控制（影响瞄准速度）", [
            ("check_interval", "检查间隔（秒）- 越小调整越频繁，速度越快"),
            ("p_factor", "P控制因子（0-1）- 越大逼近越快，但可能过冲"),
            ("max_move_per_check", "最大单次移动（像素）- 越大移动越快"),
        ]),
        ("快速定位参数", [
            ("initial_move_threshold", "初始移动阈值"),
            ("initial_wait_min", "初始等待最小时间（秒）"),
            ("initial_wait_max", "初始等待最大时间（秒）"),
        ]),
        ("微调（拟人化）参数", [
            ("fine_tune_enabled", "启用微调"),
            ("fine_tune_duration", "微调时长（毫秒）"),
            ("micro_move_range", "微调移动范围（像素）"),
        ]),
        ("算法开关", [
            ("use_compensation", "启用距离补偿"),
            ("use_prediction", "启用动量预测"),
            ("use_smoothing", "启用平滑滤波"),
        ]),
        ("算法参数", [
            ("smoothing_alpha", "平滑系数（0-1）- 越小越平滑，但响应越慢"),
            ("flight_time", "预估飞行时间（秒）"),
        ]),
        ("遮挡处理参数", [
            ("handle_occlusion", "启用遮挡处理"),
            ("max_occlusion_attempts", "最大遮挡尝试次数"),
            ("camera_up_offset", "抬高摄像头距离（像素）"),
            ("occlusion_wait_time", "抬高后等待时间（秒）"),
        ]),
        ("其他", [
            ("debug", "调试模式"),
            ("log_move_threshold", "日志移动阈值"),
        ]),
    ]

    for group_name, params in groups:
        print(f"\n【{group_name}】")
        for key, desc in params:
            value = getattr(config, key, None)
            if value is not None:
                print(f"  {desc:30}: {value}")

    print("\n" + "="*60)
    print("\n速度调整建议：")
    print("- 想让瞄准更快：减小 check_interval(0.02)、增大 p_factor(0.5)、增大 max_move_per_check(100)")
    print("- 想让瞄准更稳：增大 check_interval(0.05)、减小 p_factor(0.2)、减小 max_move_per_check(50)")
    print("- 想让响应更快：增大 smoothing_alpha(0.5)")
    print("="*60)


def get_float_input(prompt: str, current_value: float, min_val: float = None, max_val: float = None) -> float:
    """获取浮点数输入。"""
    while True:
        try:
            input_str = input(f"{prompt} [{current_value}]: ").strip()
            if not input_str:
                return current_value

            value = float(input_str)

            if min_val is not None and value < min_val:
                print(f"值不能小于 {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"值不能大于 {max_val}")
                continue

            return value
        except ValueError:
            print("请输入有效的数字")


def get_int_input(prompt: str, current_value: int, min_val: int = None, max_val: int = None) -> int:
    """获取整数输入。"""
    while True:
        try:
            input_str = input(f"{prompt} [{current_value}]: ").strip()
            if not input_str:
                return current_value

            value = int(input_str)

            if min_val is not None and value < min_val:
                print(f"值不能小于 {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"值不能大于 {max_val}")
                continue

            return value
        except ValueError:
            print("请输入有效的整数")


def get_bool_input(prompt: str, current_value: bool) -> bool:
    """获取布尔值输入。"""
    while True:
        input_str = input(f"{prompt} [{'是' if current_value else '否'}]: ").strip()
        if not input_str:
            return current_value

        input_str = input_str.lower()
        if input_str in ['y', 'yes', '是', '真', 'true', '1']:
            return True
        elif input_str in ['n', 'no', '否', '假', 'false', '0']:
            return False
        else:
            print("请输入 y/n 或 是/否")


def edit_config_interactive(config: AimConfig) -> AimConfig:
    """交互式编辑配置。"""

    print("\n开始编辑配置（直接回车保持当前值）：")
    print("-" * 60)

    # 基础参数
    print("\n【基础瞄准参数】")
    config.aim_duration = get_float_input("瞄准持续时间（秒）", config.aim_duration, 0.1, 10.0)
    config.aim_tolerance = get_int_input("瞄准容忍度（像素）", config.aim_tolerance, 10, 200)
    config.mouse_to_view_ratio = get_float_input("鼠标视角比例", config.mouse_to_view_ratio, 0.1, 3.0)

    # 持续瞄准参数 - 重点说明微调速度
    print("\n【微调速度控制】（影响瞄准速度的主要参数）")
    config.check_interval = get_float_input("检查间隔（秒）[建议: 0.02-0.1，越小调整越快]", config.check_interval, 0.01, 0.5)
    config.max_move_per_check = get_int_input("最大单次移动（像素）[建议: 50-150，越大移动越快]", config.max_move_per_check, 5, 200)
    config.p_factor = get_float_input("P控制因子[建议: 0.3-0.7，越大逼近越快，0.3较稳，0.5较快]", config.p_factor, 0.0, 1.0)

    # 快速定位参数
    print("\n【快速定位参数】")
    config.initial_move_threshold = get_int_input("初始移动阈值", config.initial_move_threshold, 1, 50)
    config.initial_wait_min = get_float_input("初始等待最小时间（秒）", config.initial_wait_min, 0.0, 0.5)
    config.initial_wait_max = get_float_input("初始等待最大时间（秒）", config.initial_wait_max, 0.0, 0.5)

    # 微调参数
    print("\n【拟人化微调参数】")
    config.fine_tune_enabled = get_bool_input("启用微调（拟人化小幅移动）", config.fine_tune_enabled)
    if config.fine_tune_enabled:
        config.fine_tune_duration = get_int_input("微调时长（毫秒）", config.fine_tune_duration, 100, 2000)
        config.micro_move_range = get_int_input("微调移动范围（像素）", config.micro_move_range, 1, 20)

    # 算法开关
    print("\n【算法开关】")
    config.use_compensation = get_bool_input("启用距离补偿（远距离向上瞄准）", config.use_compensation)
    config.use_prediction = get_bool_input("启用动量预测（预测移动目标位置）", config.use_prediction)
    config.use_smoothing = get_bool_input("启用平滑滤波（消除抖动）", config.use_smoothing)

    # 算法参数
    print("\n【算法参数】")
    if config.use_smoothing:
        config.smoothing_alpha = get_float_input("平滑系数[0.3平滑, 0.5快速响应]", config.smoothing_alpha, 0.0, 1.0)
    if config.use_compensation:
        config.flight_time = get_float_input("预估飞行时间（秒）", config.flight_time, 0.1, 2.0)

    # 遮挡处理参数
    print("\n【遮挡处理参数】")
    config.handle_occlusion = get_bool_input("启用遮挡处理（自动抬高摄像头）", config.handle_occlusion)
    if config.handle_occlusion:
        config.max_occlusion_attempts = get_int_input("最大遮挡尝试次数", config.max_occlusion_attempts, 1, 10)
        config.camera_up_offset = get_int_input("抬高摄像头距离（像素）", config.camera_up_offset, 50, 300)
        config.occlusion_wait_time = get_float_input("抬高后等待时间（秒）", config.occlusion_wait_time, 0.1, 1.0)

    # 调试
    config.debug = get_bool_input("调试模式", config.debug)

    return config


def main():
    """主函数。"""
    print("\n" + "="*60)
    print("洛克王国 - 瞄准配置编辑器")
    print("="*60)
    print("\n📍 瞄准原理：")
    print("  瞄准算法以屏幕中心为基准，检测到的精灵会自动移动到屏幕中心位置")
    print("\n⚡ 微调速度说明：")
    print("  当前觉得微调速度慢，主要受以下参数影响：")
    print("  • check_interval（检查间隔）：默认0.05秒，改小如0.02秒会更频繁调整")
    print("  • p_factor（P控制因子）：默认0.3，改大如0.5会更快逼近目标")
    print("  • max_move_per_check（单次最大移动）：默认70，改大如100会移动更快")
    print("\n🎯 推荐速度设置：")
    print("  • 快速模式：check_interval=0.02, p_factor=0.5, max_move_per_check=100")
    print("  • 平稳模式：check_interval=0.05, p_factor=0.3, max_move_per_check=70")
    print("="*60)

    # 加载当前配置
    config = AimConfig.from_file()
    print_current_config(config)

    while True:
        print("\n选项:")
        print("1. 编辑配置")
        print("2. 恢复默认")
        print("3. 保存并退出")
        print("4. 退出（不保存）")

        choice = input("\n请选择 [1-4]: ").strip()

        if choice == '1':
            config = edit_config_interactive(config)
            print_current_config(config)
        elif choice == '2':
            config = AimConfig()
            print("\n已恢复默认配置")
            print_current_config(config)
        elif choice == '3':
            if config.save_to_file():
                print("\n配置已保存！")
            else:
                print("\n保存失败！")
            break
        elif choice == '4':
            break
        else:
            print("无效选择，请重试")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
