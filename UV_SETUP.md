# uv 配置指南

## 全局配置（推荐）

```bash
# 设置清华镜像源
uv pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 设置代理（加速下载）
uv pip config set global.proxy http://127.0.0.1:7890

# 验证配置
uv pip config list
```

## 临时配置（单次使用）

```bash
# 临时使用镜像源
uv pip install <package> --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 临时使用代理
uv pip install <package> --proxy http://127.0.0.1:7890
```

## 项目级配置

在 `pyproject.toml` 中添加:

```toml
[tool.uv.pip]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

## 常用命令

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境（Windows）
.\.venv\Scripts\activate

# 安装依赖
uv pip install -e .

# 安装特定包
uv pip install <package-name>

# 查看已安装包
uv pip list

# 导出依赖
uv pip freeze > requirements.txt
```

## 故障排除

### 代理连接失败
```bash
# 检查代理是否运行
curl http://127.0.0.1:7890

# 临时禁用代理
uv pip install <package> --proxy off
```

### 镜像源问题
```bash
# 切换到官方源
uv pip config set global.index-url https://pypi.org/simple
```
