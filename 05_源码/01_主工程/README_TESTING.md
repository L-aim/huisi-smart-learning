# 测试与验收说明

以下命令均从源码包根目录执行。

## 一键测试

首次运行先执行 `.\安装依赖.ps1`，然后：

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall
```

脚本会依次启动前后端并执行：

1. 后端验收脚本；
2. 集成闭环脚本；
3. 后端单元测试；
4. 前端类型检查与生产构建；
5. Playwright 端到端测试。

如本机没有可用的 Edge/Playwright 浏览器，可先跳过 E2E：

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall -SkipE2E
```

## 分项执行

后端服务启动后，可执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python .\tests\backend_acceptance.py http://127.0.0.1:8000
python .\tests\integration_flow.py http://127.0.0.1:8000
```

后端单元测试：

```powershell
Push-Location .\backend
$env:PYTHONPATH = (Get-Location).Path
python -m unittest discover -s tests -p "test*.py" -v
Pop-Location
```

前端检查与构建：

```powershell
Push-Location .\frontend-vue
npm run check
npm run lint
npm run build
Pop-Location
```

前端 E2E：

```powershell
Push-Location .\frontend-vue
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:5173"
npm run test:e2e -- --project=msedge --workers=1
Pop-Location
```

## 验收重点

- 登录页能够进入系统；
- 所有主导航页面可访问且无白屏；
- 用户画像、资源工坊、练习诊断、知识中枢、路径推送、智能辅导和评估进化页面可正常加载；
- 无外部密钥时，受影响功能给出安全提示或使用演示回退，不泄露配置；
- 前端生产构建和后端自动化测试通过。
