# 源码包说明（慧思智学平台）

> 第十一届华为 ICT 大赛 · 中国创新赛 · 赛题 2「基于华为云 AgentArts 的 Agent 设计和应用」参赛作品源码包。
> 本目录供赛题复核复现使用；验收结论与证据见同级目录 `03_验收与测试证据/`。

## 一、目录内容

| 目录 | 内容 |
|---|---|
| `01_主工程/` | FastAPI 后端 + Vue 3 前端源码、单元测试、最小演示数据、安装与启动脚本 |
| `mcp_server/` | MCP 工具服务：`get_student_profile` / `get_role_competency` / `get_project_status`（Streamable HTTP，适配 AgentArts 网关） |
| `02_岗位能力模块/` | 岗位图谱子系统与《结构化岗位画像》，即 `get_role_competency` 的数据来源 |
| `课程讲义/` | 知识库语料（《软件需求分析与建模》讲义一） |

## 二、本包不含什么，以及为什么

- `node_modules/`、`dist/`、`.venv/`、`__pycache__/`：依赖目录与编译产物，由安装脚本生成，不随源码包提交。
- `log/`、`test-results/`、`*.bak`、根目录 `data/`：本机运行期残留（日志、验收输出、编辑备份、临时数据库）。
- `backend/.env` 实体：只附 `backend/.env.example` 空模板，密钥不随包提交。
- `backend/data/presentation_assets/*.pptx`（约 7.1 MB 的 PPT 母版）：仅供「按大纲生成 PPT」接口当作版式模板，本作品答辩与常规演示不使用。为控制压缩包体积已移出；如需验证该接口，把这个 pptx 放回该目录即可，缺失时只有该接口报错，其余功能不受影响。
- 关于 `02_岗位能力模块/`：原目录名含其他赛事名称，包内已更名为 `02_岗位能力模块`，`mcp_server/services.py` 第 14–15 行两处路径已同步指向新目录名，功能不受影响（已实测）。

## 三、快速复现（Windows）

后端：

```powershell
cd 01_主工程\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8012
# 健康检查：http://127.0.0.1:8012/api/health
```

前端（需 Node.js 18+）：

```powershell
cd 01_主工程\frontend-vue
npm ci
npm run build      # 或 npm run dev
```

一键安装与启动：`01_主工程\安装依赖.ps1` → `01_主工程\启动源码.bat`。

## 四、与本作品答辩展示对应的可复现点

| 展示效果 | 复现入口 | 实测结论 |
|---|---|---|
| 多智能体九步编排（9 个 Agent 接手、7 个独立进程） | `01_主工程\scripts\eval\test_multi_agent_real.py` | 9 步全 ok，7 个不同 PID |
| 30+ 接口与单测 | `01_主工程\backend\tests\` | `def test_` 共 41 个 |
| 评测集与工具名交叉校验 | `01_主工程\scripts\eval\run_eval.py` | 静态模式解析 MCP 工具名比对评测集 |
| 前端 11 页可点验 | `01_主工程\frontend-vue\src\pages\` | 见 `03_验收与测试证据/浏览器验收进度.md` |

> 源码包自身复测（2026-10-19）：在包目录内直接调用 `mcp_server/services.py`，`get_role_competency_data` 与 `get_student_profile_data` 均返回 `ok=True` 且带真实画像/岗位数据，证明依赖路径与数据文件在本包内自洽。

## 五、边界：本包内不能复现的部分

以下数字来自华为云 AgentArts 平台，依赖参赛队伍账号与已部署资源。本包可复现本地等价链路，平台侧原始输出见 `03_验收与测试证据/`：

- 云端 9 进程（pid 11–19）的编排实证 —— 《多Agent云端多进程实证.md》
- 平台知识库 `ict-course-kb` + 单智能体 `ict-course-kb-qa` 的命中分数 —— 《平台知识库智能体实证.md》
- 记忆库跨会话召回 —— 《记忆库接入实证.md》
- 平台「观测与优化 > 评估」8 条评测集、均分 0.76 —— 《TEST_RESULTS.md》

## 六、环境注意

- `PYTHONPATH` 必须**同时**含 `01_主工程\backend` 与本包根目录（即 `mcp_server` 所在的那一层）：九步编排要 `import mcp_server`，只给 backend 会报 `MULTI_AGENT_REGISTRY_UNAVAILABLE（ModuleNotFoundError: No module named 'mcp_server'）`。`start-dev.ps1` 已按此设置，手动起 uvicorn 时才需自己加。
- Windows 下多进程编排需要允许创建子进程；受限沙箱环境会报 `PermissionError: [WinError 5]`，请在普通用户会话中运行。
- LLM 相关接口需在 `01_主工程\backend\.env` 填入模型服务密钥（参照 `.env.example`）；未填时走 `demo_mode` 演示模板，页面功能仍可完整点验。

## 七、换一台机器复现的检查清单

| 步骤 | 命令 / 动作 | 通过标准 |
|---|---|---|
| 1. 装运行环境 | Python 3.11+、Node.js 18+、能访问 pip/npm 源 | `python -V`、`node -v` 有输出 |
| 2. 装依赖 | `01_主工程\安装依赖.ps1`（python 依赖 + `npm ci`） | 最后打印「依赖安装完成」 |
| 3. 启动 | 双击 `01_主工程\启动源码.bat` | 窗口打印 Backend `http://127.0.0.1:8000` 与 Vue `http://127.0.0.1:5173` |
| 4. 后端自检 | 浏览器开 `http://127.0.0.1:8000/api/health` | 返回 `ok: true` |
| 5. 前端自检 | 浏览器开 `http://127.0.0.1:5173/` | 首页正常渲染、控制台无红色报错 |
| 6. 九步编排 | `cd 01_主工程\backend` 后 `python ..\scripts\eval\test_multi_agent_real.py` | 打印 9 步全 ok、7 个互不相同的 PID |
| 7. 单测 | `01_主工程\scripts\run-all-tests.ps1`（或 `pytest backend\tests`） | 41 个用例通过 |

> 说明：第 2 步需要联网；第 6 步的进程数与 PID 每次运行都会变，**只要求 9 步、7 个不同 PID**，不要求具体数字。第 4–7 步全部通过即等价于本机答辩演示效果；云端平台侧数字见第五节。
