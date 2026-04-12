#!/usr/bin/env python3
"""
Interception 驱动环境检查工具

检查项目：
1. 操作系统平台（仅支持 Windows）
2. 管理员权限
3. Python 包安装
4. 驱动符号完整性
5. 驱动上下文创建

用法：
    uv run python -m src.tools.check_interception
"""
import ctypes
import json
import platform
import sys


def is_admin():
    """检查是否以管理员身份运行。"""
    if platform.system() != "Windows":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    report = {
        "success": False,
        "checks": {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "python": sys.version.split()[0],
            },
            "admin": {"is_admin": is_admin()},
            "interception_import": {"ok": False},
            "interception_symbols": {"ok": False},
            "driver_context": {"ok": False},
        },
        "suggestions": [],
    }

    # 检查 1: 操作系统
    if platform.system() != "Windows":
        report["suggestions"].append("Interception 仅支持 Windows 系统")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    # 检查 2: Python 包导入
    try:
        from interception import ffi, lib

        report["checks"]["interception_import"] = {"ok": True}
    except Exception as e:
        report["checks"]["interception_import"] = {"ok": False, "error": str(e)}
        report["suggestions"].append("Python 包未安装，运行: pip install interception")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    # 检查 3: 驱动符号完整性
    missing_symbols = []
    for symbol in ("interception_create_context", "interception_destroy_context", "interception_send"):
        if not hasattr(lib, symbol):
            missing_symbols.append(symbol)

    try:
        ffi.typeof("InterceptionKeyStroke")
    except Exception:
        missing_symbols.append("InterceptionKeyStroke")

    if missing_symbols:
        report["checks"]["interception_symbols"] = {"ok": False, "missing": missing_symbols}
        report["suggestions"].append("驱动符号缺失，重新安装: pip uninstall interception && pip install interception")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["checks"]["interception_symbols"] = {"ok": True}

    # 检查 4: 驱动上下文创建
    ctx = None
    try:
        ctx = lib.interception_create_context()
        if ctx:
            report["checks"]["driver_context"] = {"ok": True}
        else:
            report["checks"]["driver_context"] = {
                "ok": False,
                "error": "interception_create_context 返回 null",
            }
    except Exception as e:
        report["checks"]["driver_context"] = {"ok": False, "error": str(e)}
    finally:
        if ctx:
            try:
                lib.interception_destroy_context(ctx)
            except Exception:
                pass

    # 生成建议
    if not report["checks"]["admin"]["is_admin"]:
        report["suggestions"].append("[WARN] 未以管理员身份运行，请右键「以管理员身份运行」终端")

    if not report["checks"]["driver_context"]["ok"]:
        report["suggestions"].append(
            "驱动未安装或未启动\n"
            "   1. 下载驱动: https://github.com/oblitum/Interception/releases\n"
            "   2. 解压后运行 install-interception.exe\n"
            "   3. 重启 Windows\n"
            "   4. 以管理员身份重新运行此检查"
        )

    # 最终结果
    report["success"] = (
        report["checks"]["interception_import"]["ok"]
        and report["checks"]["interception_symbols"]["ok"]
        and report["checks"]["driver_context"]["ok"]
    )

    if report["success"]:
        report["suggestions"].append("Interception 环境就绪，可以运行输入测试")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
