# 模板检测器模块

## 概述

本目录包含所有基于 OpenCV 模板匹配的游戏界面检测器。

## 检测器列表

| 检测器 | 模板文件 | 检测方法 | 用途 |
|--------|----------|----------|------|
| CaptureModeDetector | capture_mode.png | Canny边缘 | 检测精灵球捕捉界面 |
| BattleModeDetector | battle_mode.png | Canny边缘 | 检测战斗界面 |
| BattleExitConfirmDetector | battle_exit_confirm.png | 灰度匹配 | 检测战斗逃跑确认框 |

## 配置加载工具

`config_loader.py` 提供统一的配置加载和坐标换算功能：

```python
from src.detectors.config_loader import load_roi_relative, rel_to_abs, load_click_point

# 加载相对坐标 (0.0-1.0)
rel_roi = load_roi_relative("capture_mode")  # (rel_x, rel_y, rel_w, rel_h)

# 转换为绝对坐标
abs_roi = rel_to_abs(rel_roi, (1280, 720))  # (abs_x, abs_y, abs_w, abs_h)

# 加载点击点坐标
click_pos = load_click_point("confirm_button")  # (rel_x, rel_y)
```

## 使用方法

### 基本用法

```python
from src.detectors import CaptureModeDetector

detector = CaptureModeDetector(
    template_path="data/templates/capture_mode.png",
    frame_size=(1280, 720),
    debug=False
)

is_match, confidence = detector.is_capture_mode(frame)
```

### 配置文件

所有检测器从 `data/templates/templates_config.json` 加载 ROI 配置：
- 相对坐标 (rel_x, rel_y, rel_w, rel_h) - 支持任意分辨率
- 绝对坐标 (abs_x, abs_y, abs_w, abs_h) - 基于 1280x720

## 检测方法对比

### Canny 边缘检测（推荐）

- 优点：抗背景干扰，只关注形状轮廓
- 缺点：对模板质量要求高
- 适用：界面元素（按钮、图标）
- 使用：CaptureModeDetector, BattleModeDetector

### 灰度匹配

- 优点：实现简单，对颜色敏感
- 缺点：易受光照影响
- 适用：弹窗、对话框
- 使用：BattleExitConfirmDetector

## 添加新检测器

1. 在 `data/templates/` 添加模板图片
2. 在 `templates_config.json` 添加 ROI 配置
3. 创建检测器类（继承或参考现有实现）
4. 使用 `config_loader` 加载配置
5. 在 `__init__.py` 导出
6. 更新本 README