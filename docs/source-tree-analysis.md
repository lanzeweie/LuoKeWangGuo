# 源代码树分析

## 项目结构

```
LuokeWangGuo/
├── .claude/                    # Claude Code 配置
│   ├── CLAUDE.md              # 项目上下文
│   ├── skills/                # BMAD 技能
│   └── rules/                 # 规则文件
│
├── .venv/                      # Python 虚拟环境
│
├── _bmad/                      # BMAD 工作流配置
│   ├── bmm/
│   ├── core/
│   └── _config/
│
├── _bmad-output/              # BMAD 输出
│   ├── implementation-artifacts/
│   │   └── 1-1-enhanced-capture-logic.md
│   └── sprint-status.yaml
│
├── components/                 # ★ UI 组件层
│   └── coordinate_picker.py   # 相对坐标选择器 GUI
│
├── data/                      # 数据目录
│   ├── dataset.yaml          # 数据集配置
│   ├── classes.txt            # 类别名称
│   ├── templates/            # CV 模板
│   │   ├── capture_mode.png
│   │   ├── battle_mode.png
│   │   ├── battle_exit_confirm.png
│   │   └── templates_config.json
│   ├── images/               # 训练图片
│   └── labels/               # 标注文件
│
├── docs/                     # 文档目录
│   ├── implementation_plan.md
│   ├── project-overview.md   # ★ 新生成
│   └── project-scan-report.json
│
├── models/                   # 模型文件
│   ├── base/                 # 基础模型
│   │   ├── yolov8n.pt
│   │   └── yolo26n.pt
│   └── trained/              # 训练模型
│       └── luoke_pet.pt     # ★ 主模型
│
├── src/                     # ★ 源代码
│   ├── __init__.py
│   ├── main.py              # ★ 主入口
│   ├── config.py            # 配置管理
│   ├── logger.py            # 日志
│   │
│   ├── core/                # 核心模块
│   │   ├── __init__.py
│   │   ├── game_logic.py     # 游戏逻辑计算
│   │   ├── state_machine.py # 状态机
│   │   └── capabilities/    # ★ 能力层
│   │       ├── __init__.py
│   │       ├── battle_mode_detector.py    # 战斗界面检测
│   │       ├── capture_mode_detector.py  # 精灵球界面检测
│   │       ├── detection.py             # YOLO 推理
│   │       ├── gdi_overlay.py           # GDI 覆盖层
│   │       ├── input_sim.py             # 输入模拟
│   │       ├── layered_overlay.py       # DWM 透明覆盖层
│   │       ├── screen_cap.py            # DX12 截屏
│   │       ├── sendinput_sim.py         # SendInput 键鼠模拟
│   │       ├── target_scoring.py        # 目标评分
│   │       ├── target_verifier.py        # 目标验证
│   │       ├── template_loader.py        # 模板配置加载
│   │       └── window_mgr.py            # 窗口管理
│   │
│   ├── actions/              # ★ 行动层
│   │   ├── __init__.py
│   │   ├── aim_and_throw.py    # 瞄准 + 投掷
│   │   ├── battle_exit.py     # 退出战斗
│   │   └── move_controller.py # WASD 移动
│   │
│   ├── strategies/          # (待实现) 策略层
│   │   ├── __init__.py
│   │
│   ├── utils/               # (待实现) 工具函数
│   │   ├── __init__.py
│   │
│   ├── tools/              # 调试工具
│   │   ├── __init__.py
│   │   ├── annotate_roi.py
│   │   ├── diagnose_window.py
│   │   └── template_captor.py
│
│   └── components/          # UI 组件
│       └── coordinate_picker.py
│
├── pyproject.toml           # 项目配置
├── README.md               # 项目说明
├── .gitignore
└── uv.lock
```

## 关键目录说明

| 目录 | 用途 | 状态 |
|------|------|------|
| `src/main.py` | 主入口，AppContext + 主循环 | ✅ 完成 |
| `src/core/capabilities/` | 底层能力：检测、截屏、输入 | ✅ 完成 |
| `src/actions/` | 高级动作：移动、投掷、战斗退出 | ✅ 完成 |
| `src/strategies/` | 业务决策策略 | ⏳ 待实现 |
| `src/utils/` | 数学工具函数 | ⏳ 待实现 |
| `models/trained/` | 训练好的模型 | ✅ 完成 |
| `data/templates/` | CV 模板和配置 | ✅ 完成 |

## 入口点

| 入口 | 命令 | 说明 |
|------|------|------|
| 主程序 | `uv run python -m src.main` | 启动主循环 |
| 窗口诊断 | `uv run python -m src.tools.diagnose_window` | 诊断窗口和截图问题 |
| 模板截取 | `uv run python -m src.tools.template_captor` | 获取 CV 模板 |
| 模型验证 | `uv run yolo val model=models/trained/luoke_pet.pt` | 验证模型 |

## 模块依赖图

```
main.py
  ├── config.py (配置)
  ├── logger.py (日志)
  ├── core/state_machine.py (状态机)
  │   ├── core/game_logic.py
  │   └── core/capabilities/*
  │       ├── detection.py (YOLO)
  │       ├── screen_cap.py (截屏)
  │       ├── window_mgr.py (窗口)
  │       ├── sendinput_sim.py (输入)
  │       └── layered_overlay.py (覆盖层)
  └── actions/*
      ├── move_controller.py
      ├── aim_and_throw.py
      └── battle_exit.py
```