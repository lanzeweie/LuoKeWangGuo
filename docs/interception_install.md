# Interception 驱动安装指南

## 问题诊断

当前问题：`interception_send()` 返回 0，表示发送失败。

## 原因

`interception` Python 包只是一个绑定库，**真正的驱动程序需要单独安装**。

## 解决方案

### 1. 下载 Interception 驱动

访问官方仓库下载驱动安装程序：
https://github.com/oblitum/Interception

或者直接下载：
https://github.com/oblitum/Interception/releases

### 2. 安装驱动

1. 解压下载的文件
2. 以**管理员身份**运行 `install-interception.exe`
3. 重启计算机

### 3. 验证安装

重启后运行测试：
```bash
uv run python src/tools/test_interception_basic.py
```

如果看到鼠标移动或输入字符 'A'，说明安装成功。

## 建议

1. **优先尝试安装 Interception 驱动** - 反检测能力最强
2. **测试实际效果** - 在游戏中测试是否被检测

## 当前状态

- ✅ Interception Python 包已安装
- ❌ Interception 驱动未安装（需要手动安装）
