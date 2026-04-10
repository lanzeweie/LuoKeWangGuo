# 项目文档索引

> 这是项目的 AI 辅助开发主入口点

## 项目概览

| 属性 | 值 |
|------|-----|
| **项目名称** | LuokeWangGuo (洛克王国半自动精灵捕捉工具) |
| **类型** | 单体应用 (Monolith) |
| **主要语言** | Python 3.9+ |
| **版本** | 0.1.0 |

## 技术栈

- **语言**: Python 3.9+
- **AI/ML**: Ultralytics YOLOv8n
- **截屏**: dxcam (DirectX12)
- **CV**: OpenCV
- **输入**: SendInput API (pywin32)
- **包管理**: uv

## 快速开始

```bash
# 安装依赖
uv sync

# 运行主程序 (需管理员权限)
uv run python -m src.main --model models/trained/luoke_pet.pt
```

> **注意**: 必须以管理员身份运行，否则 SendInput 操作会被 UAC 拦截。

## 项目文档

### 生成文档

- [项目概览](./project-overview.md)
- [源代码树分析](./source-tree-analysis.md)
- [开发指南](./development-guide.md)

### 现有文档

- [README](../README.md) - 项目主说明
- [实现计划](./implementation_plan.md) - 详细实现计划

## 核心模块

| 模块 | 状态 | 说明 |
|------|------|------|
| `src/main.py` | ✅ | 主入口，AppContext + 主循环 |
| `src/core/capabilities/detection.py` | ✅ | YOLO 推理 |
| `src/core/capabilities/screen_cap.py` | ✅ | DX12 截屏 |
| `src/core/capabilities/sendinput_sim.py` | ✅ | SendInput 键鼠模拟 |
| `src/core/capabilities/target_verifier.py` | ✅ | 多周期目标验证 |
| `src/core/capabilities/target_scoring.py` | ✅ | 目标评分和优先级 |
| `src/actions/aim_and_throw.py` | ✅ | 瞄准 + 投掷 |
| `src/actions/move_controller.py` | ✅ | WASD 移动控制 |
| `src/actions/battle_exit.py` | ✅ | 退出战斗 |
| `src/strategies/` | ⏳ | 策略层 (待实现) |
| `src/utils/` | ⏳ | 数学工具 (待实现) |

## 开发进度

| 阶段 | 状态 |
|------|------|
| 1. 环境搭建 | ✅ |
| 2. 模型训练 | ✅ |
| 3. 核心模块 | ✅ |
| 4. 策略层 | ⏳ 进行中 |
| 5. 整合测试 | ⏳ 待开始 |

**当前 Story**: Epic 1 Story 1 - Enhanced Capture Logic with Distance Judgment and Target Verification

## 重要文件

| 文件 | 路径 |
|------|------|
| 训练模型 | `models/trained/luoke_pet.pt` |
| 项目配置文件 | `pyproject.toml` |
| CV 模板目录 | `data/templates/` |

## 相关资源

- [CLAUDE.md](../.claude/CLAUDE.md) - Claude Code 项目上下文
- [_bmad-output/sprint-status.yaml](../_bmad-output/sprint-status.yaml) - Sprint 状态

---

*生成时间: 2026-04-10*