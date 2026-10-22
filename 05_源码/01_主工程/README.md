# 慧思智学平台（源码包）

本目录是可复现构建的完整源码包，主程序采用 FastAPI + Vue 3。源码、依赖锁文件、测试脚本、空敏感配置模板以及最小演示数据均已包含；依赖目录和编译产物不随源码包提交。

## 目录说明

- `backend/`：FastAPI 后端源码、单元测试与最小演示数据。
- `frontend-vue/`：Vue 3 前端源码、静态资源、端到端测试和 `package-lock.json`。
- `tests/`：后端验收与集成流程脚本。
- `scripts/`：自动化验收脚本。
- `安装依赖.ps1`：安装 Python 和 Node.js 依赖。
- `start-dev.ps1` / `启动源码.bat`：启动源码开发环境。
- `stop-dev.ps1`：停止本项目使用的本地端口。

## 环境要求

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 18 或更高版本（附带 npm）

## 首次安装

在本目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\安装依赖.ps1
```

安装脚本会执行：

```powershell
python -m pip install -r .\backend\requirements.txt
Push-Location .\frontend-vue
npm ci
Pop-Location
```

## 启动

双击 `启动源码.bat`，或在 PowerShell 中运行：

```powershell
.\start-dev.ps1
```

启动后访问：

- 前端：`http://127.0.0.1:5173`
- 后端接口文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

演示登录：

- 手机号：任意 11 位数字
- 密码：`demo123`
- 验证码：按页面显示输入（初始演示值通常为 `2VV3`）
- 建议学生标识：`demo`

## 第三方服务配置

默认配置不包含任何真实密钥。基础页面、演示数据与本地流程可直接运行；需要调用外部大模型、图像生成或数字人服务时：

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

然后仅在本机填写相应配置。请勿把含真实密钥的 `.env` 对外提交。

## 构建与验收

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall
```

也可按 [README_TESTING.md](README_TESTING.md) 分项执行。前端生产构建命令为：

```powershell
Push-Location .\frontend-vue
npm run build
Pop-Location
```

作品包中的 Windows 可执行程序由 `desktop_launcher.py` 通过 PyInstaller 构建；前端生产文件和最小演示数据在作品包中作为外部资源随程序分发。

## 提交安全说明

本包未包含真实 `.env`、版本库历史、依赖目录、缓存、日志、个人运行数据、学校标识或参赛人员信息。演示数据仅使用通用的 `demo` 标识。
