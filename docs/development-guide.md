# 开发指南

## 环境要求

| 要求 | 详情 |
|------|------|
| Python | 3.9+ |
| 操作系统 | Windows 10/11 |
| GPU | DirectX12 兼容 (如 RTX 3060 Ti) |
| 权限 | **管理员运行** (SendInput 需要) |
| 包管理 | uv |

## 安装

```bash
# 克隆项目后安装依赖
cd LuokeWangGuo
uv sync
```

## 常用命令

### 主程序

```bash
# 标准运行
uv run python -m src.main --model models/trained/luoke_pet.pt

# 调试模式 (显示更多日志)
uv run python -m src.main --model models/trained/luoke_pet.pt --debug
```

### 模型训练与验证

```bash
# 模型验证
uv run yolo val model=models/trained/luoke_pet.pt data=data/dataset.yaml

# 训练
uv run python tools/train.py
```

### 工具模块

```bash
# 模板截取 - 精灵球模式
uv run python -m src.tools.template_captor --capture

# 模板截取 - 战斗模式
uv run python -m src.tools.template_captor --battle

# 模板截取 - 两种模式
uv run python -m src.tools.template_captor --both

# SendInput 测试
uv run python -m src.core.capabilities.sendinput_sim --real-test
```

## 代码结构

### 核心模块 (src/core/capabilities/)

| 文件 | 功能 |
|------|------|
| `detection.py` | YOLO 模型推理 |
| `screen_cap.py` | DX12 屏幕截图 |
| `window_mgr.py` | 窗口管理 (客户区坐标) |
| `sendinput_sim.py` | SendInput 键鼠模拟 |
| `target_scoring.py` | 目标评分和优先级 |
| `target_verifier.py` | 多周期目标验证 |
| `capture_mode_detector.py` | 精灵球界面检测 (CV) |
| `battle_mode_detector.py` | 战斗界面检测 (CV) |
| `layered_overlay.py` | DWM 透明覆盖层 |

### 行动模块 (src/actions/)

| 文件 | 功能 |
|------|------|
| `move_controller.py` | WASD 移动控制 |
| `aim_and_throw.py` | 瞄准 + 投掷逻辑 |
| `battle_exit.py` | ESC 退出战斗 |

## 配置参数

编辑 `src/config.py` 或运行参数：

| 参数 | 说明 | 默认值 |
|------|------|-------|
| `--model` | 模型路径 | `models/trained/luoke_pet.pt` |
| `--debug` | 调试模式 | `False` |
| `--detection-interval` | 检测间隔 (秒) | `2.0` |
| `--verification-cycles` | 验证周期数 | `3` |

## 测试

```bash
# 运行测试 (需要先安装测试依赖)
uv sync --group dev
pytest
```

## 开发规范

### 代码风格
- 使用 `black` 格式化: `uv run black src/`
- 使用 `ruff` 检查: `uv run ruff check src/`

### 命名规则
- 类名: `PascalCase` (如 `TargetScorer`)
- 函数名: `snake_case` (如 `calculate_distance`)
- 常量: `UPPER_SNAKE_CASE` (如 `MAX_DISTANCE_THRESHOLD`)

### 不可变性
- 使用 `@dataclass(frozen=True)` 创建不可变数据类
- 永远创建新对象，不修改现有对象

### 坐标系统
- 所有坐标必须是**客户区相对坐标**
- 使用 `WindowManager.get_region()` 获取客户区左上角
- 鼠标/键盘操作使用客户区相对坐标

### 反作弊要求 (CRITICAL)
- 使用 `SendInput` API (不是 pynput)
- 每个操作间 80-150ms 随机延迟
- 鼠标移动使用分段轨迹 + 随机抖动
- 禁止任何内存操作

## 调试技巧

### 查看检测结果
```bash
# 运行带调试输出
uv run python -m src.main --model models/trained/luoke_pet.pt --debug
```

### 截取模板
```bash
# 截取当前屏幕作为 CV 模板
uv run python -m src.tools.template_captor --capture
```

### 测试输入模拟
```bash
# 测试 SendInput 是否正常工作
uv run python -m src.core.capabilities.sendinput_sim --real-test
```

## 常见问题

### Q: SendInput 操作无效
**A**: 确保以管理员身份运行终端

### Q: 截屏为黑屏
**A**: 检查 GPU 是否支持 DirectX12

### Q: 精灵检测不到
**A**: 
1. 检查模型路径是否正确
2. 检查游戏窗口是否获得焦点
3. 检查客户区坐标是否正确

## 相关文档

- [项目概览](./project-overview.md)
- [实现计划](./implementation_plan.md)
- [源代码树](./source-tree-analysis.md)