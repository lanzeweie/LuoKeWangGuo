#!/usr/bin/env python3
"""
瞄准算法模块测试

测试 docs/aim_algorithm.md 中阶段2的所有算法：
- 距离补偿
- 动量预测
- 平滑滤波
- 距离分类
"""

from __future__ import annotations

from src.core.capabilities.aim_algorithms import (
    calculate_drop_compensation,
    MovementPredictor,
    SmoothFilter,
    DistanceClassifier,
)


def test_drop_compensation() -> bool:
    """测试距离补偿算法。"""
    passed = 0
    failed = 0
    screen_area = 1280 * 720  # 921600

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("[Test 1] 阶梯式边界 — CLOSE 区域补偿为 0...")
    # 面积 > 1.5% 屏幕面积 (13824) → CLOSE → 补偿 0
    comp = calculate_drop_compensation(bbox_area=15000, screen_area=screen_area)
    check("15000px² (CLOSE) -> compensation=0", comp == 0)

    comp = calculate_drop_compensation(bbox_area=20000, screen_area=screen_area)
    check("20000px² (very CLOSE) -> compensation=0", comp == 0)

    print("\n[Test 2] 阶梯式边界 — FAR 区域补偿为 -25...")
    # 面积 < 0.5% 屏幕面积 (4608) → FAR → 补偿 -25
    comp = calculate_drop_compensation(bbox_area=4000, screen_area=screen_area)
    check("4000px² (FAR) -> compensation=-25", comp == -25)

    comp = calculate_drop_compensation(bbox_area=1000, screen_area=screen_area)
    check("1000px² (very FAR) -> compensation=-25", comp == -25)

    print("\n[Test 3] 线性插值 — MEDIUM 区域...")
    # 面积在 4608 ~ 13824 之间 → 线性插值
    # 中点：t = 0.5 → compensation = -25 + 0.5 * 25 = -12 (约)
    mid_area = (4608 + 13824) / 2
    comp = calculate_drop_compensation(bbox_area=mid_area, screen_area=screen_area)
    check(f"中点面积 {mid_area:.0f}px² -> compensation=-12", comp == -12)

    print("\n[Test 4] 线性插值 — 靠近 CLOSE 边界...")
    # 接近 max_area (13824)，t 接近 1.0，补偿接近 0
    near_close = 13000
    comp = calculate_drop_compensation(bbox_area=near_close, screen_area=screen_area)
    check(f"{near_close}px² -> compensation in [-3, 0]", -3 <= comp <= 0)

    print("\n[Test 5] 线性插值 — 靠近 FAR 边界...")
    # 接近 min_area (4608)，t 接近 0.0，补偿接近 -25
    near_far = 5000
    comp = calculate_drop_compensation(bbox_area=near_far, screen_area=screen_area)
    check(f"{near_far}px² -> compensation in [-25, -20]", -25 <= comp <= -20)

    print(f"\n  Subtotal: {passed} passed, {failed} failed")
    return failed == 0


def test_movement_predictor() -> bool:
    """测试动量预测算法。"""
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("[Test 1] 历史记录不足 — 单点无法预测...")
    predictor = MovementPredictor()
    predictor.update(100, 100)
    px, py = predictor.predict(flight_time=0.5)
    check("单点预测返回当前位置", px == 100 and py == 100)

    print("\n[Test 2] 匀速移动预测...")
    predictor = MovementPredictor(max_predict_step=200)
    # 手动注入时间戳以确保精确的速度计算
    # dt=0.1, v_x=100px/s, 在 max_predict_step=200 范围内
    predictor._history = [(100.0, 100.0, 0.0), (110.0, 100.0, 0.1)]

    px, py = predictor.predict(flight_time=0.5)
    # 预测：110 + 100 * 0.5 = 160
    check(f"向右匀速 -> pred_x=160 (actual {px:.1f})", abs(px - 160) < 1)
    check(f"Y 不变 -> pred_y=100 (actual {py:.1f})", abs(py - 100) < 1)

    print("\n[Test 3] 最大步长限制...")
    predictor = MovementPredictor(max_predict_step=50)
    # 极端跳变：速度 = (1000-0)/0.05 = 20000px/s，远超 max_predict_step
    predictor._history = [(0.0, 0.0, 0.0), (1000.0, 0.0, 0.05)]

    px, py = predictor.predict(flight_time=1.0)
    # 速度被限制在 50px/s，预测 = 1000 + 50*1 = 1050
    check(f"最大步长限制 -> pred_x=1050 (actual {px:.1f})", abs(px - 1050) < 1)

    print("\n[Test 4] reset 清空历史...")
    predictor = MovementPredictor()
    predictor.update(100, 100)
    predictor.update(200, 200)
    predictor.reset()
    check("reset 后历史为空", len(predictor._history) == 0)

    print(f"\n  Subtotal: {passed} passed, {failed} failed")
    return failed == 0


def test_smooth_filter() -> bool:
    """测试平滑滤波算法。"""
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("[Test 1] 首帧返回原始值...")
    f = SmoothFilter(alpha=0.3)
    sx, sy = f.process(100, 100)
    check("首帧 x=100", sx == 100)
    check("首帧 y=100", sy == 100)

    print("\n[Test 2] 一阶低通滤波公式...")
    f = SmoothFilter(alpha=0.3)
    f.process(100, 100)  # 初始化 last=100
    sx, sy = f.process(200, 200)  # 新输入 200

    # smoothed = 100 + 0.3 * (200 - 100) = 130
    check(f"smoothed = 100 + 0.3*(200-100) = 130 (actual {sx:.1f})", abs(sx - 130) < 0.1)
    check(f"smoothed y = 130 (actual {sy:.1f})", abs(sy - 130) < 0.1)

    print("\n[Test 3] 多次迭代收敛...")
    f = SmoothFilter(alpha=0.3)
    f.process(0, 0)
    # 持续输入同一值，应该逐渐收敛
    for _ in range(20):
        sx, sy = f.process(100, 100)
    check(f"20次迭代后接近目标值 (actual {sx:.2f})", abs(sx - 100) < 1)

    print("\n[Test 4] alpha=1 时不平滑（直接返回）...")
    f = SmoothFilter(alpha=1.0)
    f.process(0, 0)
    sx, sy = f.process(100, 100)
    check("alpha=1 -> 直接返回新值", sx == 100 and sy == 100)

    print("\n[Test 5] 无效 alpha 抛出异常...")
    try:
        SmoothFilter(alpha=0)
        check("alpha=0 应抛出异常", False)
    except ValueError:
        check("alpha=0 抛出 ValueError", True)

    try:
        SmoothFilter(alpha=1.5)
        check("alpha=1.5 应抛出异常", False)
    except ValueError:
        check("alpha=1.5 抛出 ValueError", True)

    print("\n[Test 6] reset 重置状态...")
    f = SmoothFilter(alpha=0.3)
    f.process(100, 100)
    f.process(200, 200)
    f.reset()
    check("reset 后 last_x 为 None", f._last_x is None)
    check("reset 后 last_y 为 None", f._last_y is None)

    print(f"\n  Subtotal: {passed} passed, {failed} failed")
    return failed == 0


def test_distance_classifier() -> bool:
    """测试距离分类算法。"""
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("[Test 1] 默认 1280x720 分类...")
    clf = DistanceClassifier()
    check("far_threshold = 4608 (0.5%)", abs(clf.far_threshold - 4608) < 0.1)
    check("near_threshold = 13824 (1.5%)", abs(clf.near_threshold - 13824) < 0.1)

    print("\n[Test 2] FAR 分类...")
    clf = DistanceClassifier()
    check("1000px² -> FAR", clf.classify(1000) == "FAR")
    check("4607px² -> FAR", clf.classify(4607) == "FAR")

    print("\n[Test 3] MEDIUM 分类...")
    clf = DistanceClassifier()
    check("5000px² -> MEDIUM", clf.classify(5000) == "MEDIUM")
    check("10000px² -> MEDIUM", clf.classify(10000) == "MEDIUM")

    print("\n[Test 4] CLOSE 分类...")
    clf = DistanceClassifier()
    check("14000px² -> CLOSE", clf.classify(14000) == "CLOSE")
    check("50000px² -> CLOSE", clf.classify(50000) == "CLOSE")

    print("\n[Test 5] 自定义分辨率...")
    clf = DistanceClassifier(screen_width=1920, screen_height=1080)
    area = 1920 * 1080
    expected_far = area * 0.005
    expected_near = area * 0.015
    check(f"1920x1080 far_threshold={expected_far:.0f}", abs(clf.far_threshold - expected_far) < 0.1)
    check(f"1920x1080 near_threshold={expected_near:.0f}", abs(clf.near_threshold - expected_near) < 0.1)

    # 在 1920x1080 下，3000px² 仍为 FAR
    check("1920x1080 下 3000px² -> FAR", clf.classify(3000) == "FAR")

    print(f"\n  Subtotal: {passed} passed, {failed} failed")
    return failed == 0


def run_all_tests() -> bool:
    """运行所有测试。"""
    print("=" * 60)
    print("瞄准算法模块测试 (docs/aim_algorithm.md 阶段2)")
    print("=" * 60)

    results = []

    results.append(("距离补偿", test_drop_compensation()))
    results.append(("动量预测", test_movement_predictor()))
    results.append(("平滑滤波", test_smooth_filter()))
    results.append(("距离分类", test_distance_classifier()))

    print("\n" + "=" * 60)
    print("总体结果")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("所有测试通过！")
    else:
        print("存在失败的测试！")
    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    run_all_tests()
