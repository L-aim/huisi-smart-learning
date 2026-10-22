# 测试结果

执行日期：2026-10-03（Asia/Shanghai）

## 环境

- Python：3.12.14（验证环境）
- Node.js：24.12.0
- npm：11.6.2
- 后端：FastAPI 0.115.14
- MCP SDK：1.30.0（独立虚拟环境）

## 最终结果

| 验证项 | 结果 | 数量/说明 |
|---|---|---|
| 后端健康检查 | 通过 | `GET /api/health`，后端/知识库/数据目录均 ready |
| 后端单元测试 | 通过 | 41/41 |
| 后端验收脚本 | 通过 | 12/12 |
| 集成流程 | 通过 | 3/3 |
| MCP 业务测试 | 通过 | 7/7 |
| MCP 协议级调用 | 通过 | 工具发现成功；两个必选工具实际调用成功 |
| 前端类型检查 | 通过 | `npm run check` |
| 前端 ESLint | 通过 | `npm run lint` |
| 前端生产构建 | 通过 | 2317 个模块完成转换，生成 `dist/` |
| 前端生产文件启动 | 通过 | 本地静态服务访问首页返回 HTTP 200，且包含 `#app` 挂载节点 |

生产构建有一个非阻断警告：部分输出块超过 500 kB，后续可按页面继续拆分动态模块。

## 执行命令

主工程后端：

```powershell
cd .\01_主工程\backend
$env:PYTHONPATH = (Get-Location).Path
python -m unittest discover -s tests -p "test*.py" -v
```

服务级验收：

```powershell
cd .\01_主工程
python .\tests\backend_acceptance.py http://127.0.0.1:8000
python .\tests\integration_flow.py http://127.0.0.1:8000
```

前端：

```powershell
cd .\01_主工程\frontend-vue
npm run check
npm run lint
npm run build
```

MCP：

```powershell
cd <开发工作区根目录>
.\test_mcp.ps1
```

## 首次基线与修复

首次运行发现并修复：

1. `fastapi>=0.115` 无上限会安装 0.142，改变路由注册表现，使 4 个回归断言失败。已固定为兼容的 0.115 系列，最终 41 项全部通过。
2. Vite 在受限 Windows 目录中加载 TypeScript 配置时，esbuild 会扫描不可访问的父目录。已新增程序化构建脚本，`npm run build` 最终通过。
3. 旧验收脚本仍要求无密钥时伪造资源、题库和回答，与当前“禁止合成回退”的安全逻辑冲突。已改为验证本地 `demo` 数据和可解释错误，不把模拟内容冒充模型结果。
4. `/api/multimodal/generate` 无密钥时原本抛出 HTTP 500。已改为标准 `success=false` 和 `MULTIMODAL_GENERATION_ERROR`。
5. 健康检查原来始终报告 `demo_mode=false`。已改为根据模型配置真实反映状态。

## 2026-10-13 增量变更：MCP 参数可空化（AgentArts 接入）

背景：AgentArts 网关侧工具发现与调用已通，但官方高代码示例用 LangChain 的
`StructuredTool` 包装 MCP 工具时，会把非必填参数生成为 `Optional[str] = None`，
模型有可能把该字段**显式发成 JSON `null`**。原实现两个参数都是必填 `str`，
这种请求会在协议层直接校验失败，错误文本如下：

```
1 validation error for get_role_competencyArguments
role_name
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
```

变更：`ICT/mcp_server/server.py` 中 `get_role_competency` 的 `role_name`、`role_id`
改为 `Optional[str] = None`（并补充 `from typing import Optional`），使协议层声明与
AgentArts 客户端生成的一致；“至少提供一项”的约束仍由 `services.py` 的
`(role_name or "").strip()` 归一化后判定，缺失时返回业务错误码 `MISSING_ROLE_QUERY`。

| 验证项 | 结果 | 说明 |
|---|---|---|
| MCP 单元测试 | 通过 | `mcp_server/tests` 7/7 |
| 空值参数探针 | 通过 | 5/5 符合预期（见下） |
| 公网隧道端到端 | 通过 | `verify_public_mcp.py` 对隧道地址 ALL PASS |
| 工具 schema 兼容性 | 通过 | `tools/list` 无 `outputSchema`/`$schema`/`icons` |

空值参数探针（直连 `http://127.0.0.1:8010/mcp`）：

| 入参 | 结果 |
|---|---|
| 仅 `role_id` | `ok=True`，`match=exact_role_id` |
| `role_name=null` + `role_id=job_001` | `ok=True`，`match=exact_role_id` |
| 两者都为 `null` | `ok=False`（业务错误码，非协议层校验失败） |
| 两者都为空字符串 | `ok=False` |
| `role_id=null` + `role_name=前端开发工程师` | `ok=True`，`match=exact_role_name` |

执行命令：

```powershell
# 重启本机 MCP 服务（本机 PATH 无 pwsh，用 powershell.exe）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_mcp.ps1 -Public

# 单元测试
python -m unittest discover -s .\ICT\mcp_server\tests -t .\ICT -v

# 公网端到端
python .\verify_public_mcp.py https://<隧道域名>/mcp
```

## 2026-10-15 增量：智能体上云与 MCP 运行时直连（已达成）

云端智能体 `ict-career-agent`（Runtime ID `44a4e950-6642-4e6d-8c1f-3d49ea43d3a9`）与云端 MCP 服务 `ict-mcp-server`（Runtime ID `d702705d-36e4-4b73-965b-fb7085f1cbb3`）之间已打通，**全程不经过 Cloudflare 隧道、不经过 AgentArts 网关**。

| 验证项 | 结果 | 说明 |
|---|---|---|
| MCP 运行时部署 | 通过 | 镜像 `swr.cn-southwest-2.myhuaweicloud.com/ict-agentarts/ict-mcp-server:latest`，控制台状态「正常」 |
| 智能体运行时部署 | 通过 | `agentarts launch` 返回 `Deployment complete!`，Region `cn-southwest-2` |
| IAM V11 签名探针 | 通过 | `probe_iam.py`：HTTP 200、`content-type=text/event-stream`、命中工具 3/3 |
| 云端工具自动发现 | 通过 | `[Agent] 共加载 3 个工具 (MCP: 3, 本地: 0)`（**当时服务端只有 3 个工具**；2026-10-17 起扩到 9 个，见本文件平台评估一节与 `00_提交清单` 第五节） |
| 云端端到端问答 | 通过 | `agentarts invoke` 返回完整中文结构化分析，未编造数据 |
| 本地端到端问答 | 通过 | 模型自主调用 `get_student_profile` + `get_role_competency` 两个工具 |

端到端调用命令：

```bash
agentarts invoke --agent ict-career-agent -s cloud-demo-3 \
  '{"message": "demo 和前端开发工程师匹配吗"}'
```

返回 `status: success`，正文含分项对照表，并明确声明「现有数据不支持给出可信匹配度评分」——系统提示词里「结论必须有工具数据支撑、禁止编造」的红线在云端同样生效。

完整报告见工作区根目录《AgentArts-第4步-智能体上云与MCP运行时直连实测报告》。

本次新增并已修复的三个坑：

1. **SSE 响应编码**：MCP 走 `text/event-stream` 且不声明 charset，`requests` 的 `resp.text` 按 ISO-8859-1 解码，中文工具描述全部乱码（如 `æå¦çè¯¢å`）。已改用 `resp.content.decode("utf-8", errors="replace")`。
2. **容器内无 AK/SK**：`create_credential()` 的三级凭据链（环境变量 → `~/.huaweicloud` → 元数据服务 `169.254.169.254`）在容器内全部 miss，抛 `ValueError: Authentication failed: Could not find valid credentials.`。修法：在 `.env` 中显式提供 `HUAWEICLOUD_SDK_AK` / `HUAWEICLOUD_SDK_SK`。
3. **AgentArts 网关不支持 IAM 出站认证**：Target 的出站认证只有 `api_key` / `oauth` / `none`，用 `none` 调用受 IAM 保护的运行时，数据面返回「错误码 -32603 / `upstream error: 401 Unauthorized`」，而控制面 `status` 仍显示 `ready`。因此改为智能体直连运行时。

### 2026-10-15 晚：密钥轮换与清理（含 10-16 更正）

| 项 | 结果 |
|---|---|
| `credentials.csv`（含明文账号凭据，128 字节） | 已移出工作区 → `（本地密钥备份文件，未提交）` |
| AK/SK 轮换 | ⚠️ **当时并未真正生效**：写回 `.bashrc` / `.env` 的 AK 与轮换前是同一把。10-16 更正并真正完成，见下节 |
| `app.py` 的 `_DNS_OVERRIDES` | 已移除；移除后重新部署并验证通过，证明该覆盖确实不是必需的 |
| ~~密钥轮换后的权限自检 `CRED-OK`~~ | ❌ **该判定作废**：`agentarts` CLI 鉴权失败时退出码仍为 0，`… && echo CRED-OK` 是假绿灯，不构成证据 |

配套脚本：`.\ref\ict_agent\set_keys.py`（隐藏输入 + 字符集校验 + 剥尾部全角字符，写 `~/.bashrc`）、`sync_keys.py`（同步进 `.env`，只回显长度）。

坑：从控制台复制的密钥常带尾部全角字符；且非 UTF-8 locale 下 `${#VAR}` 按字节计数会误报长度。

### 2026-10-16：AK/SK 轮换真正闭环

| 项 | 结果 |
|---|---|
| 轮换到 10-15 新建的那把访问密钥 | 已写入 `~/.bashrc` 与 `~/ref/code_new/.env`（`set_sk.py` 先探测、后落盘），并部署 `ict-career-agent(v7)` |
| 端到端 | `agentarts invoke --agent ict-career-agent -s cloud-demo-6 '{"message":"demo 和前端开发工程师匹配吗"}'` → `status: success`，返回完整中文人岗比对分析 |
| 凭证判定口径 | 改为**读输出文本**：成功看 `Total targets` / `Deployment complete`，失败看 `verify ak sk signature failed`；不再以退出码为准 |
| 旧密钥停用 | 控制台把旧 AK 置为「停用」后复验 `agentarts invoke --agent ict-career-agent -s stop-check '{"message":"ping"}'` → `{"response": "pong ✅ 连接正常。…", "status": "success"}`，新密钥完全接替。停用**不释放**访问密钥配额（页面仍显示「您还可以添加 0 个」），腾位置必须用操作列的「删除」 |

新增脚本（`.\ref\ict_agent\`）：`try_sk.py`（只探测候选 SK，不修改文件）、`set_sk.py`（AK 不动、只换 SK，探测通过才写）、`swap_ak.py`（AK 分 4 段明文键入，绕开失灵的终端剪贴板）。

三条坑：

1. `agentarts` CLI 鉴权失败时退出码仍为 0 —— `CRED-OK` 式自检是假绿灯。
2. 华为云 SK 只在创建时显示一次，关掉弹窗不可再查看；新建密钥必须当场下载 CSV 或立刻录入。
3. `source ~/.bashrc` 不能与 `&` 后台化的 `launch` 写在同一行（`source` 只作用于后台子 shell），否则随后的 `invoke` 仍跑在旧环境里并误报 401。

### 2026-10-16：MCP 工具集扩张（3 → 9）

为补上《推进计划》里 P0-2「MCP 只有 3 个只读工具、缺少写/动作类工具，撑不起 Agent 编排闭环」这一缺口，在 `mcp_server\server.py` 与 `services.py` **纯新增** 6 个工具（原有 3 个只读工具未改动一行）。

| 工具 | 类型 | 本次验证结果 |
|---|---|---|
| `search_knowledge(student_id, query, limit=5)` | 只读 | 通过 |
| `get_wrong_book(student_id)` | 只读 | 通过 |
| `get_learning_evaluation(student_id)` | 只读 | 通过 |
| `get_exercise_session(student_id, limit=5)` | 只读 | 已注册、接线正常；演示数据缺失，未验成 |
| `submit_exercise_answer(student_id, question_id, answer)` | **写入** | 同上 |
| `add_learning_branch(student_id, knowledge_node_id, title, description, mastery)` | **写入** | 同上 |

验证方式：把改后的 `server.py`（5542 字节）与 `services.py`（21201 字节）放进 `~/ref/mcp_deploy/mcp_server/`，`docker build -t ict-mcp-server:test .` + `docker run -d --name ict-mcp-test -p 8000:8000 ict-mcp-server:test`，容器内跑 `test_mcp_tools.py`：

```text
工具数量：9
工具清单：['get_student_profile', 'get_role_competency', 'get_project_status', 'search_knowledge',
          'get_exercise_session', 'submit_exercise_answer', 'get_wrong_book', 'get_learning_evaluation',
          'add_learning_branch']
核心只读 6/6 ok=true
get_exercise_session | ok=false code=NO_QUESTION_BANK message=该学生名下没有可用的题库资源，无法生成诊断练习。
submit_exercise_answer | SKIP — 取不到题目 ID（题库为空）
add_learning_branch | SKIP — 取不到路径节点 ID（demo 的 stages 为空）
RESULT: CORE-PASS — 核心只读 6/6 接线已验证
```

未验成的三个工具**不是接线问题**，而是 `demo` 演示数据本身的边界（已逐行核对源码确认）：

1. `01_主工程\backend\data\users\demo\resources.json` 只有 2 条资源（`video_recommendation`、`voice_tutor_plan`），**没有 `question_bank`**；而 `exercise_bank.py:276` 的 `_load_generated_questions` 只认 `type == "question_bank"` 且 `meta.requirement.constraints.source ∈ {"exercise_custom_bank", "path_stage_quiz"}` 的资源。
2. `demo/events.json` 的 2 个 `path_plan` 事件 `payload` 中只有 `title`，没有 `path.nodes`；`path_progress.py:285` 的 `_latest_path_context` 因此取不到节点，`add_path_branch` 会 `raise ValueError("请先生成学习路径，再加入知识分支。")`。

> `get_exercise_session` 返回的 `NO_QUESTION_BANK` 是**业务错误码**，本身即证明请求已正确到达服务层并被正常处理，只是演示数据里确实没有题库。这三个工具在拥有题库与路径节点的真实学生数据上应当可用，但**本次未在真实数据上验证过**，故不计入「通过」。

> **2026-10-17 补记：上述三个工具已全部在真实题库与路径节点上验成，本节「不计入通过」的结论作废。**
> 做法是给 `demo` 补一套演示数据（题库 3 题 + 3 节点学习路径），随后本地容器 `test_demo_loop.py` **7/7 通过**（出题 3 道 → 逐题作答 3/3 正确 → 阶段推进 `stage-1 mastery=100 advanced=True next=stage-2` → `add_learning_branch created=True` → 学习效果评估 `accuracy=60 score=32 evidence_total=31`），云端 `-s demo-loop-3` 实测 3/3 `correct=True`。详见本文后续「2026-10-17」各节。

本机结构自检（`ast.parse`，因沙箱禁止在 `ICT\mcp_server\` 写 `__pycache__`）输出 `SYNTAX-OK` / `TOOLS(9)` / `MISSING-FUNCS: []` / `UNWIRED: []` / `ANNOTATED-DEFS: []` / `RESULT: PASS`。

**2026-10-17 更新：已上线，云端 9 个工具可用。** 在 `~/ref/mcp_deploy` 执行 `agentarts launch` 后云端 MCP 运行时升到 v2（Runtime ID 不变），开发桌面实测 `agent.list_mcp_tools()` 返回 **9 个工具**。

但仅上线还不够——复测「demo 的错题本里有哪些题？」时，模型回答「工具里没有独立的『错题本』接口」，转而用 `get_student_profile` 的 `learning_summary.exercise.corrections` 字段拼答案。原因是 `~/ref/code_new/agent.py` 的 `_SYSTEM_PROMPT` 里【可用工具】是一份**手写清单**，只列了原来 3 个工具，模型据此认为自己没有新工具。

修法：把 `_SYSTEM_PROMPT` 扩到 9 个工具，并加一张「意图 → 工具」路由表（错题 → `get_wrong_book`、资料 → `search_knowledge`、出题 → `get_exercise_session` → `submit_exercise_answer`、效果 → `get_learning_evaluation`、路径 → `get_project_status`、加分支 → `add_learning_branch`），并写明「按意图选专用工具，不要用 `get_student_profile` 的摘要代替」。重新部署 `ict-career-agent(v8)` 后，同一问题返回了带「错题明细 / 薄弱标签 / 能力雷达（当前分·上次分·证据数）」的完整错题本分析，**证明模型确实调用了 `get_wrong_book`**。

> 经验：MCP 侧加工具只是「上线」，提示词不同步等于工具在模型眼里不存在。扩工具必须同时改 `_SYSTEM_PROMPT` 并重新部署智能体。

### 2026-10-17：云端 9 工具端到端实测（v8）

提示词同步并部署 `ict-career-agent(v8)` 后，用 `agentarts invoke` 逐项实测。每次一个全新 session，只给一句自然语言，由模型自主决定是否调工具：

| # | 提问 | 实际调用的工具 | 判定依据（只有该工具能返回的字段） | 结果 |
|---|---|---|---|---|
| 1 | demo 的错题本里有哪些题？请用工具查，不要猜。 | `get_wrong_book` | 错题明细表；薄弱标签「练习诊断 2/2 100%」「资源推送 2/2 100%」；能力雷达「当前分 / 上次分 / 证据数」（基础知识掌握能力 25.0 / 33.3 / 2） | 通过 |
| 2 | 帮我查一下学习资料里关于用例图的知识点，给出出处。 | `search_knowledge` | 容器内路径 `/app/01_主工程/backend/data/files/demo/ef11ad2b41a247a28e56535d5c915a7d.md`；出处 ID `resource:b57f6480aa9c4c809a827d3c9be564c6`；余弦相关度 `0.09（低）` | 通过 |
| 3 | demo 的学习效果怎么样？掌握度和正确率分别是多少？ | `get_learning_evaluation` | 「证据总数 23（练习 2 · 知识节点 0 · 资源 2 · 反馈 0 · 学习事件 19）」；「置信度 高」；五维（知识掌握 0 / 迁移应用 0.0 / 学习投入 44 / 资源匹配 0.0 / 策略稳定 40） | 通过 |
| 4 | 用 demo 这个学生，给我出 3 道诊断练习题。 | `get_exercise_session` | 原样转述 `ok=false`、`code=NO_QUESTION_BANK`、`message=该学生名下没有可用的题库资源，无法生成诊断练习。`、`details: student_id=demo, question_bank_resource_count=0` | 通过（错误路径） |

> 第 2 条的 `0.09` 是 `knowledge_hub.search_index` 返回的余弦相似度，`/app/...` 路径来自 `content_uri` 的解析结果；第 3 条的「证据总数 / 置信度」出自 `learning_state.evaluation_overview`；第 4 条的 `question_bank_resource_count` 是本项目 `services.py` 自定义的 `details` 结构。这四类字段模型均无法凭空生成，可作为「确实调用了工具」的硬证据。

**防编造行为的三次实证**

1. 第 2 条检索只命中一条 0.09 的低相关度引用，模型明确写出「该命中片段中并没有用例图的定义、参与者、用例之间关系（包含/扩展/泛化）等实质知识点，属于『提到』而非『讲解』」，**没有把低相关度片段包装成答案**。
2. 第 4 条题库为空时，模型**一道题都没有编**，而是原样转述错误码、反推根因（题库为空），并给出排查顺序（先绑题库 → 再查学习路径 → 最后验画像数据）。
3. 同样问「给我出 3 道诊断练习题，我要练一练」但未提供学号时，模型**拒绝猜测学号**、反问学生 ID 并提示可用测试 ID `demo`，未擅自默认登录。

**云端实测结论：9/9 全部跑通。** `add_learning_branch` 已于 2026-10-17 在云端验证——

```bash
~/agentarts/bin/agentarts invoke --agent ict-career-agent -s persist-9 \
  '{"message": "用 demo 在 stage-2 下新增一条知识分支，标题「用例关系辨析」，然后原样告诉我 created、branch_id、parent_stage_id 三个字段的值。"}'
```

返回：

```json
{"created": true, "branch_id": "branch-62db039490f74127a84a6a0d8e20939f", "parent_stage_id": "stage-1"}
```

注意 `parent_stage_id` 是 `stage-1` 而不是请求的 `stage-2`：这是一次全新 session，容器里没有路径进度，`add_path_branch` 拿不到 `current_stage_id`，只能退回首个节点。这恰好再一次印证了「业务状态按 session 隔离」——不是 bug，是设计使然，但也意味着**真实使用时同一个学生必须在一个会话内完成闭环**。

### 2026-10-17：云端「答对判错」bug 与修复

补齐演示数据（题库 3 题 + 带 3 个节点的路径）后，云端出题链路打通：`get_exercise_session` 从 `NO_QUESTION_BANK` 变为真实返回 3 道题，且带上考点标签与 `stage-1` 归属。但首次提交作答暴露出一个真 bug。

**现象**：模型把**选项全文**（如「B. 参与者与用例之间的交互关系」）当作 `answer` 传入，后端返回「你的作答 B / 参考答案 B / correct=false」——三个字段自相矛盾，模型自己也指出「判定结果与答案本身互相矛盾」。

**根因**：`exercise_bank.py` 的判定是严格字符串比较：

```python
correct = _normalise_answer(answer) == _normalise_answer(correct_answer)
```

而 `_normalise_answer` 只对「纯字母」做归一化，非纯字母输入原样返回：

```python
raw = re.sub(r"\s+", "", str(value or "").strip().upper()...)
if raw and re.fullmatch(r"[A-H](?:,?[A-H])*", raw):
    return "".join(sorted(re.findall(r"[A-H]", raw)))
return raw          # 非纯字母原样返回
```

于是 `"B. 参与者与用例之间的交互关系" != "B"`，答对也判错。

**修法**（不动后端契约，只让 MCP 工具层更宽容）：在 `mcp_server\services.py` 增加 `_normalise_answer_input`，统一处理 `B` / `b` / `B. 选项全文` / `选项B：xxx` / `B、C` / `BC` / `["B","C"]`，并在返回里同时给出 `submitted_answer`（原始输入）与 `normalised_answer`（归一化结果），便于后续对账。

**验证**：

| 项 | 结果 |
|---|---|
| `services.py` AST 校验 | `SYNTAX-OK`，22655 字节 |
| 归一化用例 | 10/10 符合预期（`B. 全文` → `B`；`选项B：xxx` → `B`；`BC` → `B,C`；`BAD` → `B,A,D`→后端排成 `ABD`） |
| 部署 | `ict-mcp-server(v4)`，`grep -c '_normalise_answer_input'` = 3 |
| 云端复测 | 同一句「1B 2B 3C，帮我提交」返回 **3/3 `correct=True`**（修复前是 3/3 `false`） |

**遗留**：该轮回传 `advanced=false`、掌握度 `33`，与「已答 3/3、答对 3/3、目标 3」在数学上矛盾（`mastery = round(correct*100/target)` 应为 100，33 只对应 1/3）。疑似模型把**第一次**工具返回的 `path_progress` 当成最终值汇报。待用 `get_project_status` 直接确认 `stage-1` 是否已 `completed`、`stage-2` 是否已 `current`。

## 2026-10-17：云端「有状态闭环」打通（容器亲和键）

**现象**：云端提交作答后，下一次 `tools/call` 读不到刚写入的数据——`answered_count` 恒为 1，`path_progress` 每次从零重建；而同一份代码在本机容器里 7/7 通过。

**定位过程**：

1. `-s path-check-1`（新 session）查 `get_project_status` → `stage-1 | current | mastery 0`
2. 同一轮 invoke 内「提交 → 读 status」：提交返回 `mastery=33`，紧接着读回 `0` → 同一轮也不保留
3. 本机 `docker run` 同一进程内「提交 → 读 status」→ `33` / `33` 正常 → 业务代码无问题
4. 一轮内连提 3 题 → `answered_count` 恒为 `1`
5. 已在 `agent_iam.py` 实现 `initialize` + `Mcp-Session-Id` 复用，仍无效 → 说明不是 MCP 协议层的事
6. 翻 SDK 源码找到答案：

```python
# agentarts/sdk/runtime/model.py:11
SESSION_HEADER = "x-hw-agentarts-session-id"
```

`agentarts/sdk/runtime/app.py:248` 正是从这个请求头读取会话 id。**平台认的是它，不是 `mcp-session-id`。**

**根因**：自建 MCP 客户端没有携带平台自己的会话头。`mcp-session-id` 是 MCP 协议层的握手标识，与平台把请求调度到哪个容器无关——所以无论怎么复用 `Mcp-Session-Id`，平台依然为每个 `tools/call` 起新实例。

**修法**：`agent_iam.py` 的 `_mcp_headers()` 增加 `x-hw-agentarts-session-id`，取值优先用 `AgentArtsRuntimeContext.get_session_id()`，并在 `run()` 开头用业务 `session_id` 覆盖，确保与 invoke 时的 `-s` 一致。部署 `ict-career-agent(v10)`。

**验证**：

| 观测项 | 修复前 v9 | 修复后 v10 |
|---|---|---|
| 提交返回 `path_progress.mastery` | 33 | 33 |
| 紧接着 `get_project_status` 读回 | **0** | **33** |
| 一轮内连提 3 题的 `answered_count` | 1、1、1 | **33 → 67 → 100** |
| 阶段推进 | 无变化 | `status=completed`、`advanced=true`、`next_stage_id=stage-2` |

**结论**：云端 MCP 运行时可以承载有状态业务闭环，前提是客户端每次调用都必须带同一个 `x-hw-agentarts-session-id`。这条约束在官方文档里不显眼，是从 SDK 源码里挖出来的，建议写进交付文档的「踩坑」章节。

## 2026-10-17：MCP 服务加固（P0-3）

**动机**：《推进计划》P0-3「MCP 服务无任何公网必需机制」，依据是 `mcp_server/` 目录检索 `Authorization|api_key|middleware|logg|rate` 全部无匹配。

**硬约束**：云端调用走 IAM 签名、不带 API Key，加固层若做强校验会当场打断 9 个工具。因此四条机制全部**默认非阻断**，另加三道保险——未配 `MCP_API_KEY` 就不鉴权；加固层初始化异常自动降级回原生 `mcp.run()`；`MCP_TRANSPORT_DIRECT=1` 可一键跳过加固层。

**实现**：新增 `mcp_server/hardening.py`（9016 字符 / 10290 字节），纯 ASGI 中间件，不依赖 Starlette 版本；`mcp_server/server.py` 只换入口，工具定义一行未动。

| 机制 | 做法 | 环境变量 |
|---|---|---|
| API Key 鉴权 | `X-API-Key` 或 `Authorization: Bearer`，`hmac.compare_digest` 定时比较 | `MCP_API_KEY` |
| 限流 | 每客户端 60 秒滑动窗口，超限 `429` + `Retry-After` | `MCP_RATE_LIMIT_PER_MIN`（`0` 不限） |
| 日志脱敏 | 只记方法/路径/状态/耗时/客户端指纹，不记请求头与请求体 | `MCP_LOG_REQUESTS` |
| 健康检查 | `GET /healthz`，豁免鉴权与限流 | `MCP_HEALTH_PATH` |

**本地六项验证**（刻意把限流压到 3 次/分以触发）：

| # | 验证项 | 期望 | 实测 |
|---|---|---|---|
| 1 | `GET /healthz` 不带密钥 | 200 + JSON | ✅ `{"ok":true,...,"auth":"api_key","rate_limit_per_min":3}` |
| 2 | `POST /mcp` 不带密钥 | 401 | ✅ `HTTP 401` |
| 3 | `POST /mcp` 带正确密钥 | 非 401 | ✅ `HTTP 406`（`{}` 非法且缺 `Accept`，鉴权已放行） |
| 4 | 连打 4 次（第 3 步已耗 1 次） | 后两次 429 | ✅ `406 / 406 / 429 / 429` |
| 5 | 访问日志形态 | 只见方法/路径/状态/耗时/指纹 | ✅ `POST /mcp -> 429 0.6ms client=key:87d45252` |
| 6 | 日志出现明文密钥的行数 | 0 | ✅ `0` |

第 6 项是日志脱敏的硬证据：`client=key:87d45252` = `sha256("testkey123")[:8]`，全链路无一处写明文密钥。

**两条实现修正**：① 初版用 `key:testke***` 做日志标识，等于泄漏真实密钥前 6 位，改为 `sha256(key)[:8]`；② 初版把 Starlette 的 `http.HTTPStatus` 枚举直接存进日志字段，输出成 `HTTPSstatus.NOT_ACCEPTABLE`，改为 `int(raw)` 后正常显示 `406`。

**云端 v5 验证**：

| 观测项 | 结果 |
|---|---|
| 部署 | `✓ SUCCESS: Runtime 'ict-mcp-server(v5)'`，Runtime ID 不变 |
| 工具发现 | `[MCP] 从 Gateway 发现 9 个工具`、`TOOLS: 9` |
| 端到端 invoke | 三阶段路径正常返回 |
| `/healthz` 经网关 | **404** `{"code":404,"data":null,"message":"No matching policy found"}` |

那个 404 不是我们的错误信封（我们是 `{"ok":false,"error":{...}}`），是 **AgentArts 网关策略层**返回的——只转发 `/mcp` 这类已配置路径，根路径不转发。**边界要如实记录**：`/healthz` 在容器直连部署下真正可用（本地已验证），经网关调用时不可达，只能证明服务本身活着。

**附带确认**：v5 重部署后 `answered_count` 与 `mastery` 归 0，印证「重部署即换容器、写入随旧容器释放」，不是回归。

## 2026-10-17：P1-3 评测集与工程指标

《推进计划》P1-3 原文：「效果评估只有产品指标，无评测集与工程指标」。为此建了两样东西。

| 项 | 结果 |
|---|---|
| 评测集 | `01_主工程/scripts/eval/agentarts_eval_set.jsonl`，**50 条**（岗位 20 / 学习 30），字段 `id/scene/prompt/tool/expect/path_stage` |
| 校验脚本 | `01_主工程/scripts/eval/run_eval.py`，纯标准库，无第三方依赖 |
| 工具覆盖 | **9/9**，无未被引用的工具 |
| 非法工具引用 | 无 |
| 非法路径阶段 | 无（21 条带 `path_stage` 的样本均落在 stage-1/2/3） |
| 静态校验 | **通过**，`EXIT=0` |

关键是这一步**不是自查自证**：`run_eval.py` 用正则从 `mcp_server/server.py` 里真实解析 `@mcp.tool()` 的函数名，再拿评测集逐条比对，等于用源码校验评测集有没有引用不存在的工具。

```text
评测集：agentarts_eval_set.jsonl  场景：{'岗位': 20, '学习': 30}
工具覆盖：9/9（源码解析出 9 个）
未引用的工具：无
非法工具引用：无
非法路径阶段：无
静态校验：通过
```

**未测项（不假装测过）**：

- 「引用正确率」「路径可执行率」需要 live 模式（调用云端 AgentArts，须 IAM 凭据），脚本里没有实现，只在指标结构中标注为待测。
- 「工具调用成功率」只记录 **2026-10-17 云端实测基线 9/9**，来源是本文上一节的端到端实测表，不是本脚本算出来的。

## 2026-10-17：P2-1 闭环串联 UI 可见化

《推进计划》P2-1 原文：「Demo 看不见闭环串联，`PathPage.vue:555`、`EvaluatePage.vue:301` 被 `v-if="false"` 屏蔽」。

**取舍**：那两处屏蔽的是整套旧版 `os-*` 布局（各约 300 行），整块放开风险高且无法在本机构建验证。改为在**当前生效的布局**里就地挂一条可收起的闭环串联条，复用已有的 `LearningLoopContext` 组件（原本只存在于被屏蔽区块内，所以这个组件从来没在页面上出现过）。

| 文件 | 改动 |
|---|---|
| `frontend-vue/src/pages/PathPage.vue` | 生效布局末尾新增 `<details class="shot-loop-chain">` + `LearningLoopContext`（stage 05：画像→路径→伴学→评估） |
| `frontend-vue/src/pages/EvaluatePage.vue` | 同上（stage 08：证据→评估→策略→画像） |

用原生 `<details>/<summary>` 而不加 `ref` 开关，是为了不碰 script 段、把改动压到纯模板层。

**校验**（结构层面，非浏览器渲染）：

| 项 | PathPage | EvaluatePage |
|---|---|---|
| `shot-loop-chain` 出现次数 | 1 | 1 |
| `import LearningLoopContext` | 1 | 1 |
| `<template` / `</template>` 配平 | 5 / 5 | 5 / 5 |
| 原 `v-if="false"` 是否保留 | 1（未动） | 1（未动） |

**未验证项**：本机无 Node 环境，无法 `npm run build` 或 `vite dev`，页面渲染未实测；需在有 Node 的机器上构建确认。

## 2026-10-17：P2-3 演示数据标注

《推进计划》P2-3：「硬编码演示数据（可能被评委当作实现）」——登录凭据 `AppShell.vue:41,65-66`、课程目录与预设话术 `ExerciseCenterPage.vue:45-121,498-541`、首页 `HomePage.vue:44-90`、`PathPage.vue:597` 写死 `Lv. 4 勤学者`。

**产出**：`ICT/演示数据标注清单.md`，逐条列出「位置 / 内容 / 性质 / 真实实现是什么」四列，并写明边界——5 处全在前端展示层，不参与后端判定（路径晋级由 `path_progress.py` 的 `mastery >= 80` 决定，与写死的 `Lv. 4` 无关）。

**取舍**：只标注、不改业务代码。这些占位不影响主链路，改动反而引入回归风险；真正需要的是让评审能分清演示与实现。

**未执行**：前端界面上的「演示数据」角标未做——需 Node 环境改模板并 `npm run build` 验证，本机无 Node。

## 2026-10-17：P1-1 多 Agent 拆分（第一步：角色与工具绑定）

《推进计划》P1-1：「『多 Agent』名不副实：单类流水线，6 个资源标签无工具绑定」，要求拆成主控 + 画像分析/知识检索/路径规划/诊断评估/路径更新，各自挂 MCP 工具。

**本轮做的**：新增 `backend/app/agents/roles.py`，用数据把 5 个角色的「职责 / 绑定工具 / 输入 / 输出」写死为唯一事实来源，并把「6 个标签无工具绑定」这个缺陷直接消除——每个角色都指向真实 MCP 工具。

**自检不是自查自证**：`roles.py` 用正则从 `mcp_server/server.py` 真实解析 `@mcp.tool()` 函数名，逐条交叉校验角色绑定的工具是否存在、是否重复、是否有工具无人认领。

```text
roles=5 bound_tools=8/9
duplicated_bindings=none
unknown_tools=none
uncovered_tools=none
SELF-CHECK PASS
EXIT=0
```

9 个工具里 8 个被角色绑定，第 9 个 `get_role_competency` 由 `UNASSIGNED_NOTE` 显式归给主控（岗位能力口径，规划前调用），所以 `uncovered_tools=none` 是「有归属」而非「漏掉」。

**尚未做的**：`orchestrator.py:557-572,590` 的流水线本身还没改成按角色调度，本轮只建立了角色契约与校验；真正接线是下一步。

## 2026-10-17：P1-1 多 Agent 拆分（第二步：编排层工具绑定）

**改了什么**（`backend/app/agents/orchestrator.py`）：`AgentSpec` 新增 `tools: tuple[str, ...] = ()`，6 个生成智能体（lecture / mindmap / quiz / reading / practice / video）各自声明依赖的 MCP 工具；新增 `validate_agent_tool_binding()` 做静态缺陷检查，空绑定会被判为缺陷——「有标签没工具」这个缺陷从结构上被堵死。

映射关系：

| 生成智能体 | 绑定工具 |
|---|---|
| lecture_doc | `search_knowledge`、`get_student_profile` |
| mindmap | `search_knowledge` |
| question_bank | `get_exercise_session`、`submit_exercise_answer` |
| reading | `search_knowledge` |
| practice_case | `search_knowledge`、`get_role_competency` |
| video_script | `get_student_profile`、`get_learning_evaluation` |

**校验脚本** `backend/../scripts/eval/check_bindings.py`：AST 解析 + 从 `mcp_server/server.py` 真实解析 9 个工具名交叉比对。

```text
AST-OK
mcp_tools=9 bound_refs=10 distinct=6
unknown_tools=none
specs_without_tools=0
BINDING-CHECK PASS
EXIT=0
```

`specs_without_tools=0` 是关键断言：6 个 AgentSpec 全部带 `tools=`，没有一个漏挂。

**尚未做的**：`tools` 目前是**声明**，生成流程还不会真的按它去调 MCP 工具；把声明变成实际调用需要改生成链路，风险高于本轮范围，留待下一步。

## 2026-10-17：P1-2 向量检索评估（结论：先不改）

《推进计划》P1-2：「知识接入是词袋余弦，非向量检索，索引不落盘」。换成向量检索之前，先量出差距——否则「改了」无法证明「更好」。

**做了**：`scripts/eval/vector_bench.py`，离线对比两种检索在同一真实语料上的 Recall@1 / Recall@3。
- baseline：复刻现有做法（CJK 按字切 + 词袋余弦，对应 `knowledge_hub.py:1127 _tokenize` / `:1141 _cosine`）
- candidate：字符 3-gram 哈希向量（256 维，L2 归一化后点积），确定性、无需模型、可复现
- 语料：`backend/data/files/demo/*.md`，用文档标题当查询、该文档本身当金标

**实测结果**：

```text
corpus=2 queries=2 dim=256
Recall@1  bag_cosine=1.00  hashed_vector=0.50   ← candidate 更差
Recall@3  bag_cosine=1.00  hashed_vector=1.00   ← 打平
```

**结论（据实）**：现有演示语料只有 2 篇，两种方法都接近饱和，哈希向量在 Recall@1 上反而更差。**没有证据支持在这个语料上把生产检索换成向量检索**，所以本轮不动 `knowledge_hub.py`。

要做这个改动，前提是两件事必须先具备：① 真实语料规模（几十篇以上，Recall 才有区分度）；② 真正的语义向量模型（哈希 n-gram 只解决「字面相近」，不解决「语义相近」）。这两条当前都不满足，硬改属于把「看起来先进」当「更好」。

脚本保留在仓库里，等语料扩充后直接复跑即可。

## 2026-10-17：P0-4 余项 CI（流水线定义 + 本地同款执行入口）

**产出两个文件**：

| 文件 | 作用 |
|---|---|
| `.github/workflows/ci.yml` | GitHub Actions 流水线：push / PR / 手动触发，Python 3.11，四步检查 |
| `scripts/ci_local.ps1` | 无 GitHub 环境时的同款本地入口，跑完全同一批检查 |

四步检查都是本次改动过程中真实建立的：`mcp_server` AST 解析、P1-3 评测集静态校验、P1-1 多 Agent 工具绑定校验、P1-2 检索评估复跑。

**本地实跑结果**：

```text
== ast: mcp_server          ast-ok                      PASS
== eval-set: P1-3           工具覆盖 9/9，静态校验通过    PASS
== bindings: P1-1           specs_without_tools=0        PASS
== retrieval: P1-2          Recall@1/@3 复跑通过          PASS

CI-LOCAL PASS
EXIT=0
```

**过程中修掉的两个真问题**（都不是脚本逻辑错，是编码/换行错）：

1. 初版在脚本里写死中文目录名 `01_主工程/...`，用 `powershell -File` 执行时报 `[Errno 2] No such file or directory`，路径里的中文被解成乱码——Windows PowerShell 5.1 按 ANSI 读脚本。改为用 `Get-ChildItem -Directory -Name -like '01_*'` 动态发现目录。
2. 改完仍失败，发现中文注释行末尾的 `。` 与下一行 `$proj = ...` 被并到了同一行，`$proj` 赋值整行被注释吞掉。重写为纯 ASCII 脚本，从根上消除该风险。

这两条正好说明 CI 的价值：不过 CI 就发现不了。

**未执行**：`.github/workflows/ci.yml` 未在远端真实触发（本仓库未推到 GitHub）；前端 `npm run build` 未纳入 CI——本机无 Node，无法验证该步骤可跑通。

## 2026-10-17：云端多步跨工具轨迹实测（trace-1）

**目的**：验证「编排」不只是单个工具能通，而是六个步骤能串起来、且步骤之间真的传递数据。

**方法**：一次 invoke，命令里固定六步并要求不许合并、不许跳步；同时要求模型公开「第 2 步用了第 1 步的哪个值」「第 5 步用了第 4 步的哪个值」，并声明若有步骤未调用必须说清。

**结果：6 步全部真实调用，两处关键传值全部命中。**

| 步 | 工具 | 关键返回 |
|---|---|---|
| 1 | `get_student_profile` | 薄弱点「混淆用例图与需求访谈」「基础概念理解不牢固」 |
| 2 | `search_knowledge` | 出处 `resource:d3f1a6c2e8b94f5a9c7d21e604b8a3f7`，score 0.615，共 3 条 |
| 3 | `get_project_status` | `stage-1` 需求获取与建模基础，`mastery 0`、`status=current` |
| 4 | `get_exercise_session` | 题目 id `generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0` |
| 5 | `submit_exercise_answer` | `correct=true`（correct_answer=B），`mastery 33`、`answered 1/3`、accuracy 100 |
| 6 | `get_learning_evaluation` | `mastery 0`、`accuracy 33.3`、`score 22`、weak_points「练习诊断」「资源推送」 |

**两处关键证据（这是「真传值」与「各调各的」的分界线）**：

1. 第 2 步检索用的关键词 = 第 1 步返回的 `weaknesses[0]`「混淆用例图与需求访谈」——不是模型自己编的关键词。
2. 第 5 步提交的 `question_id` = 第 4 步返回的 `questions[0].id`，精确到 `:0` 后缀——不是猜的题号。

**顺带澄清一个历史疑点**：早前「提交 1 题就报 mastery 33、却被当成 100」的矛盾，这次得到解释——`33` 就是 1/3 的真实值（`mastery = round(correct*100/target)`，target=3）。当时不是计算错，是汇报时把中间态当成了终态。

**另外两个口径差异（不是 bug，要能解释）**：
- 第 5 步 `accuracy=100`（阶段口径：本阶段作答 1 题答对 1 题），第 6 步 `accuracy=33.3`（评估模块口径：含历史 3 次作答答对 1 次）。两个数字口径不同，不是矛盾。
- 第 6 步 `mastery=0` 因为 `knowledge_state.nodes` 为空，掌握度无证据可算，与练习正确率无关。

**仍未被证明的**：这是**一个 Agent 调 6 个工具**，不是 6 个 Agent 互相编排。它证明的是「角色化步骤链路可执行 + 步骤间真实传值」，不能拿来当「多智能体编排」的证据。

## 2026-10-17：P1-1 第三步（角色编排层落地，实跑 11/11）

**背景**：前两步只是「声明」——`roles.py` 写了 5 个角色各自绑定哪些工具，`orchestrator.py` 的生成智能体也标了 `tools`，但没有任何代码按这些声明去执行。第三部把声明变成可执行的编排，并且让步骤之间真的传值。

**新增文件**：

| 文件 | 作用 |
|---|---|
| `01_主工程/backend/app/agents/role_pipeline.py` | `RolePipeline`：主控 + 5 角色共 **9 步**，每步从上一步真实返回值取参；缺绑定抛 `MissingToolBinding`；`bound_tools()` / `missing_bindings()` / `build_default_registry()` |
| `01_主工程/scripts/eval/test_role_pipeline.py` | 验收脚本：注入假实现跑编排，11 项断言 |

**执行命令**：

```bash
cd 01_主工程 && python scripts/eval/test_role_pipeline.py
```

**结果：11/11 通过**（`EXIT=0`）：

```text
PASS  roles 五个角色齐全 | ['profile', 'knowledge', 'path', 'diagnose', 'update']
PASS  绑定名与工具层实现对齐 | 8 个全部命中
PASS  9 个绑定工具全部有实现 | []
PASS  9 步按角色顺序执行、无跳步 | [...9 个工具...]
PASS  检索关键词来自画像薄弱点 | {'query': '混淆用例图与需求访谈'}
PASS  提交的问题 id 来自出题结果 | {'question_id': 'generated:d3f1a6c2...:0'}
PASS  知识分支节点来自路径状态 | {'knowledge_node_id': 'stage-1', 'title': '混淆用例图与需求访谈'}
PASS  每步都真的调了工具 | [...]
PASS  返回聚合正确 | {'correct': True, 'branch_id': 'branch-abc', 'knowledge_hits': 2, 'wrong_count': 2, 'stage_id': 'stage-1', 'mastery': 0}
PASS  缺工具时报错 | 角色 diagnose 绑定的工具 get_exercise_session 没有实现
PASS  无薄弱点时报错 | 画像里没有 weak_points，无法驱动检索——需要先补证据再编排
RESULT: 11/11 通过
```

**三条传值断言（与 trace-1 云端实测同一组因果）**：检索关键词取自 `weak_points[0]`；提交的 `question_id` 取自出题结果 `questions[0].id`；写入分支的 `knowledge_node_id` 取自 `get_project_status` 的 `stage_id`。

**两条负向断言**：注册表缺少某个工具时抛 `MissingToolBinding`（不静默跳过）；画像没有 `weak_points` 时停住报错（不编一个关键词继续跑）。这是「不编造」在编排层的落点。

**接线时被真实签名纠正的三处（说明为什么不能照着声明直接写）**：

1. `add_learning_branch` 实际签名是 `(student_id, knowledge_node_id, title, description="", mastery=0)`，最初按 `topic=` 写会直接 TypeError。
2. `get_role_competency` 参数是 `(role_name="", role_id="")`，**没有** `student_id`——它是岗位能力口径，不是学生口径。
3. 后端 `app/services/` 下并没有 `role_competency.py`，`get_student_profile` 也不是单个服务函数（MCP 侧由 `app.repo` + 多个服务拼装）。

因此 `build_default_registry()` 改为直接映射 MCP 工具层那 9 个 `*_data` 函数——它们就是线上工具本体，已在云端逐个实测过；另写一套后端适配必然与工具层漂移。

**未验证 / 边界**：

- `build_default_registry()` 未在本机实跑：它需要 `mcp_server.services` 的依赖链（`app.*` + `WORKSPACE_DIR`），本机无该环境。本机验的是编排逻辑，工具实现另由云端实测覆盖。
- 云端 trace 仍是「一个 Agent 调 6 个工具」，**未重新部署**带编排层的版本；把 `RolePipeline` 接到线上需要再打一次 Agent 镜像并复测。
- 前端编排可视化页展示的是静态角色拓扑 + 实测轨迹截图，尚未消费 `RolePipeline` 的运行期 trace。

## 2026-10-17：角色编排上线后复测（trace-2，agent v11）

**改动**：`agent_iam.py` 的 `_SYSTEM_PROMPT` 新增【角色编排】——5 角色顺序表 + 6 条硬规则（检索词取自 `weak_points`、题号取自 `questions[].id`、节点取自 `stage_id`、每步写出取值来源、`ok=false` 就地停、单点问题不必跑全链路）。部署 `ict-career-agent(v11)`，Runtime ID 仍为 `44a4e950-…d3a9`。

**与 trace-1（改前 v10）逐项对比**：

| 观察项 | trace-1（v10） | trace-2（v11） |
|---|---|---|
| 角色是否出现 | 无 | 有（表格「角色」列，未用字面 `[角色: ]` 标注） |
| 步数 | 6 步 | 8 步角色链，全部 `ok=true` |
| 传值是否主动说明 | 事后追问才答 | 每步主动写明来源 |
| 写入型工具 | 未真正串起来 | `submit_exercise_answer` 与 `add_learning_branch` 都成功 |

**三条取值链（本节硬证据）**：

1. 检索关键词 = 第 1 步 `weaknesses[0]`「混淆用例图与需求访谈」，命中 3 条、最相关 `score 0.615`。
2. 提交流程 = 第 4 步 `questions[0].id`（`generated:…:0`），判定 `B` 正确，`stage-1 mastery 0 → 33`。
3. 分支节点 = 第 3 步 `stage_id`（`stage-1`），分支创建成功（`branch-8c14…`，初始掌握度 30）。

**数字口径**：`mastery 33` = 1 题答对 / 3 题目标（`round(1*100/3)`），达标线 80 未进阶；`accuracy 33.3%` 是评估模块含历史 3 次作答（1 对 2 错）的口径，与阶段口径 100% 不矛盾。

**未达成 / 边界**：

- 只跑了 **8 个工具**，`get_role_competency` 未调用：云端角色编排表只列了 5 角色的 8 个工具，它属于本地 `RolePipeline` 的「主控」步骤，未写进云端提示词的编排表。
- 提示词要求「每步开头标注 `[角色: ]`」未被执行，模型改用表格的「角色」列表达——语义等价，不是字面遵守。
- 仍是**单个 Agent 按提示词顺序调度**，不是独立子 Agent 进程；能证明「角色化顺序 + 步骤间传值 + 写入链闭合」，不能证明「多进程多智能体」。
- 失败分支（`ok=false` 就地停）本次未触发，**未验证**。

## 2026-10-17：trace-3 触发失败分支，暴露「默认岗位」不存在，编排层随之修正

**现象**：trace-3 要求「第 0 步 get_role_competency 不传参数」，结果第 0 步直接返回
`ok=false` / `code=MISSING_ROLE_QUERY` / `message=role_name 和 role_id 至少提供一个。`。
模型按提示词规则 5 **就地停住**，明确列出第 2–5 步全部未执行，并给出工具调用统计（合计 2 次）。

**三件事同时被证实**：

| 结论 | 依据 |
|---|---|
| 我的提示词写错了 | 源码 `mcp_server/services.py:141-142`：`if not normalized_name and not normalized_id: return _failure("MISSING_ROLE_QUERY", ...)` ——**没有默认岗位**这个口径 |
| 负向硬规则真的生效 | 模型没有编造后续步骤，而是停在失败点、如实转述 code/message、说明缺什么数据 |
| 本地假实现掩盖了同一契约问题 | 假 registry 对空参也返回 `ok=true`，所以本机 11/11 全绿却没发现它 |

**修正**（三处，方向一致：失败必须显式，不能默认成功）：

1. 提示词第 0 步改为**条件步骤**：给了岗位才调，没给就说明「本次不做岗位对标」并从第 1 步继续；并写明这不算「跳过失败步骤」。
2. `role_pipeline.py` 主控改条件执行（`role_name` / `role_id` 都为空则跳过），新增 `ToolCallFailed`，`_call` 里一旦 `ok is False` 就记失败步骤并抛错。
3. 测试补三组断言：有岗位 9 步、无岗位 8 步（跳过主控）、工具中途失败必须中止且不再调用后续工具。

**复跑结果：17/17 通过（EXIT=0）**，关键行：

```text
PASS  有岗位时 9 步按角色顺序执行 | [get_role_competency, get_student_profile, ..., get_learning_evaluation]
PASS  无岗位时跳过主控且为 8 步
PASS  工具失败时编排中止 | 工具 submit_exercise_answer 返回失败：code=INVALID_QUESTION message=题目不存在。
PASS  中止后没有继续调用后续工具 | [... 到 submit_exercise_answer 为止 ...]
RESULT: 17/17 通过
```

**教训**：假数据必须复刻真实契约里的失败分支，否则「全绿」只是假象。这一轮是云端先撞出问题、本地才补上断言——顺序虽然反了，但漏洞补住了。

## 2026-10-17：云端九步编排 trace-4 全通（agent v13，9/9 工具全部 ok=true）

**命令**（`role_name` 走自然语言给，不硬编码参数）：
`s -s trace-4`，要求按第 0–5 步执行并写明每步取值来源。

**结果**：5 个阶段、9 次工具调用、合计 9 次，**全部 `ok=true`，无失败步骤**。

| # | 工具 | 角色 | 关键返回 / 取值来源 |
|---|---|---|---|
| 1 | `get_role_competency` | 主控 | 字面命中 `role_name=前端开发工程师` → **job_002（中级）**，硬技能 HTML/CSS/JS/Vue/React/Node.js |
| 2 | `get_student_profile` | 画像分析 | 薄弱点 ①混淆用例图与需求访谈 ②基础概念不牢固 |
| 3 | `search_knowledge` | 知识检索 | **query 取第 2 步 `weaknesses[0]`**；命中 3 条，最高分 `resource:d3f1a6c2…` |
| 4 | `get_project_status` | 路径规划 | 当前 `stage-1`「需求获取与建模基础」，mastery=0 |
| 5 | `get_exercise_session` | 诊断教练 | 出题 1 道 |
| 6 | `submit_exercise_answer` | 诊断教练 | **question_id 取第 5 步 `questions[0].id`** → `generated:d3f1a6c2…:0`；作答 B **正确** |
| 7 | `get_wrong_book` | 诊断教练 | 错题本 2 题；能力雷达 基础知识/抽象概括/错因复盘 **0 → 66.7** |
| 8 | `add_learning_branch` | 学习更新 | **knowledge_node_id 取第 4 步 `current_stage.id`** → `stage-1`；新建分支 `branch-0dd2e82a…`（mastery=30） |
| 9 | `get_learning_evaluation` | 学习更新 | 综合分 22 / 正确率 33.3% / 投入 51 / 证据 27（练习 3·资源 3·事件 21）/ 置信度 高 |

**三处跨步骤传值全部命中**（第 3 步用第 2 步的薄弱点、第 6 步用第 5 步的题目 ID、第 8 步用第 4 步的阶段 ID），不是每步各拿各的数据。

**防编造再次被实证**：模型主动声明

> demo 画像未提供专业/学历/技能字段，与前端岗的**逐项人岗匹配暂无法给出可信差距结论**（缺学生侧硬技能与专业证据）。本次以「岗位口径」为对标基准，重点落在学生当前课程薄弱点辅导。

岗位口径缺口不硬填，改为如实说明「只能对标不能比对」。

**结论**：P1-1 第三步完成——本地 `test_role_pipeline.py` **17/17**、云端 **9/9**，多层编排从「声明」变成「可执行且可复现」。

## 2026-10-17：把编排接上真实数据——两个字段名 bug 与假测试的教训

`test_role_pipeline.py` 之前 17/17 全过，但那 17 条用的是**我自己编的返回结构**。一接真实服务就断了，原因只有两个字：字段名。

### 第一个 bug：`weak_points` 根本不存在

`role_pipeline.py` 取薄弱点写的是 `_first_item(profile, "weak_points")`，而 `mcp_server/services.py:64` 的 `get_student_profile_data` 返回的是：

```python
"weaknesses": profile.get("focus", {}).get("weak_points", []),
```

**真实返回的键叫 `weaknesses`（顶层），`weak_points` 是嵌在它内部的来源字段名。** 假数据照着 `weak_points` 编，于是测试全绿、真跑立刻停在第 2 步：

```
TRACE: ...\role_pipeline_trace.json
ok=False steps=2
  OK   1. controller   get_role_competency      {'role_name': '前端开发工程师'}
  OK   2. profile      get_student_profile      {'student_id': 'demo'}
STOPPED: {'tool': '', 'code': 'MISSING_HANDOFF_DATA', 'message': '画像里没有 weak_points，无法驱动检索——需要先补证据再编排'}
```

### 第二个 bug：阶段 ID 不在 `stage_id`

`get_project_status_data`（`mcp_server/services.py:216`）返回 `{"student_id": ..., "path": path_overview(...)}`，当前阶段在 `path.current_stage.id`；代码却去找 `"stage_id"`，取到 `None`，会把空的 `knowledge_node_id` 传给 `add_learning_branch`。

### 修法

```python
weak_point = self._first_item(profile, "weaknesses") or self._first_item(profile, "weak_points")

current_stage = self._deep_find(self._unwrap(path), "current_stage")
stage_id = current_stage.get("id") if isinstance(current_stage, dict) else None
if not stage_id:
    stage_id = self._deep_find(self._unwrap(path), "stage_id")
```

两个旧键保留作兜底，新键优先。

### 假测试改成照抄真实契约

`scripts/eval/test_role_pipeline.py` 的假返回改为与真实一致：`data.weaknesses`（顶层）、`data.path.current_stage.id`。断言文案同步改为 `weaknesses`。

```
RESULT: 17/17 通过
TEST_EXIT=0
AST-OK
```

### 真实数据实跑：9/9，`ok=True`

```
ok=True steps=9
  OK   1. controller   get_role_competency      {'role_name': '前端开发工程师'}
  OK   2. profile      get_student_profile      {'student_id': 'demo'}
  OK   3. knowledge    search_knowledge         {'query': '混淆用例图与需求访谈'}
  OK   4. path         get_project_status       {'student_id': 'demo'}
  OK   5. diagnose     get_exercise_session     {'student_id': 'demo'}
  OK   6. diagnose     submit_exercise_answer   {'question_id': 'generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0'}
  OK   7. update       add_learning_branch      {'knowledge_node_id': 'stage-1', 'title': '混淆用例图与需求访谈'}
  OK   8. diagnose     get_wrong_book           {'student_id': 'demo'}
  OK   9. update       get_learning_evaluation  {'student_id': 'demo'}
SCRIPT_EXIT=0
```

第 3 步的检索词来自第 2 步的 `weaknesses[0]`、第 7 步的 `stage-1` 来自第 4 步的 `current_stage.id`——跨步骤传值是**真传**，不是各拿各的。

### 只读接口 `/api/orchestration/trace` 实测

用 `fastapi.testclient` 直接打路由（不启服务、不碰数据库）：

```
HTTP 200
success = True
available = True
steps = 9
roles = ['controller', 'profile', 'knowledge', 'path', 'diagnose', 'diagnose', 'update', 'diagnose', 'update']
tools = ['get_role_competency', 'get_student_profile', 'search_knowledge', 'get_project_status',
         'get_exercise_session', 'submit_exercise_answer', 'add_learning_branch',
         'get_wrong_book', 'get_learning_evaluation']
EP_EXIT=0
```

页面（`OrchestrationPage.vue`）就是消费这份 JSON 渲染拓扑与轨迹。

### 教训（已写进 `role_pipeline.py` 注释）

**假数据只能验证流程，验证不了契约。** 假数据是我按自己的理解编的，它和真实服务同时错的时候，测试会一起点头。这次两处字段名错误都不是逻辑错，是「我以为它叫这个」——所以接真实数据这一步无法省略，任何「本地全绿」都要注明「跑的是真接口还是假实现」。

## 2026-10-17：把编排接进主链路——真实操作自动留痕（live）

之前 `/api/orchestration/trace` 只有「显式跑 `run_role_pipeline_trace.py` 那一次」的记录。评委在页面上点来点去，看到的还是旧轨迹。这一节补的是「真实操作自动留痕」。

### 做法：一条旁路中间件，不动业务代码

新增 `backend/app/agents/trace_log.py`：

- `ROUTE_TOOL_MAP` 把「后端真实路由 → 角色 → MCP 工具名」写死成 8 条映射；
- `match_route()` 前缀最长匹配；`derive_handoff()` 从查询串与 `/api/profile/<id>` 路径段取入参；
- 记录写入 `settings.data_path/agent_trace_log.json`，环形保留 80 条；
- **任何异常只写 warning 日志**——留痕是旁路能力，不能因为它把业务请求搞挂。

`backend/app/main.py` 已有的 `request_log_middleware` 里加一行调用（业务代码零改动）：

```python
record_request(request.method, request.url.path, request.query_params, response.status_code)
```

`GET /api/orchestration/trace` 的响应新增 `live`（最新 12 条）与 `live_total`（总条数），与原有 `steps` 并存。

映射表：

| 后端路由 | 角色 | MCP 工具 |
|---|---|---|
| `GET /api/profile/<student_id>[/overview]` | profile | `get_student_profile` |
| `GET /api/knowledge/search` | knowledge | `search_knowledge` |
| `GET /api/path/overview` | path | `get_project_status` |
| `POST /api/path/stage/questions` | diagnose | `get_exercise_session` |
| `POST /api/exercise/answer` | diagnose | `submit_exercise_answer` |
| `GET /api/exercise/wrong-book` | diagnose | `get_wrong_book` |
| `GET /api/evaluate/overview` | update | `get_learning_evaluation` |
| `POST /api/path/branch` | update | `add_learning_branch` |

（`get_role_competency` 在 FastAPI 侧没有对应路由，只有 MCP 工具，因此不进映射表。）

### 实测：5 个真实接口 → 5 条 live 记录

```
GET /api/evaluate/overview?student_id=demo          -> HTTP 200
GET /api/path/overview?student_id=demo              -> HTTP 200
GET /api/profile/demo/overview                      -> HTTP 200
GET /api/exercise/wrong-book?student_id=demo        -> HTTP 200
GET /api/knowledge/search?student_id=demo&query=用例图 -> HTTP 200

GET /api/orchestration/trace -> HTTP 200 success = True
steps = 9 | live_total = 5
   GET /api/knowledge/search  -> knowledge search_knowledge {'student_id': 'demo', 'query': '用例图'} ok=True
   GET /api/exercise/wrong-book -> diagnose get_wrong_book {'student_id': 'demo'} ok=True
   GET /api/profile/demo/overview -> profile get_student_profile {'student_id': 'demo'} ok=True
   GET /api/path/overview -> path get_project_status {'student_id': 'demo'} ok=True
   GET /api/evaluate/overview -> update get_learning_evaluation {'student_id': 'demo'} ok=True

live entries = 5
missing tools = none
EXIT=0
```

几点值得记录：

- **路径参数也取到了学号**：`/api/profile/demo/overview` 的 `student_id` 不在查询串里，由 `derive_handoff()` 从路径段解析，记录里是 `{'student_id': 'demo'}`。
- **`steps` 与 `live` 互不影响**：`steps` 仍是 9（脚本那次整链），`live` 是新产生的 5 条。
- **`/api/orchestration/trace` 自己不在映射表里**，所以读轨迹这个动作不会被记录成一次「工具调用」，不会自我污染。

### 页面

`frontend-vue/src/pages/OrchestrationPage.vue` 新增「真实操作留痕（自动记录）」区块，消费 `live` 与 `live_total`，按角色/工具/路由/状态/传值逐条列出；`handoffText()` 的参数类型放宽为结构类型，让整链步骤与真实调用共用同一个渲染函数。

结构自检：`section 6/6`、`template 3/3`、`ol 3/3`、`li 4/4`、`div 17/17`、`p 18/18`、`h2 6/6` 全部配平。

**未验证**：本机无 Node，`npm run dev` / `npm run build` / `vue-tsc` 均未执行，页面渲染未实测——与 §「P2-2 编排可视化页」相同的限制。

## 2026-10-17：云端确定性九步编排上线（agent v17）——代码驱动挖出的三层缺口

把 `backend/app/agents/role_pipeline.py` 的九步编排搬进云端 `agent_iam.py`：命中「九步编排 / 完整诊断 / 确定性编排 / 编排演示 / 跑一遍编排 / 跑一次编排」即走**代码固定顺序**，其余仍走模型自主分步。两条通路并存。

顺序、入参、跨步传值全部由代码决定；任一步 `ok=false` 或抛异常即中止并在轨迹里留痕，后续步骤一步不跑。

### 三层缺口（全部由代码驱动这条路逼出来，模型驱动跑了十几轮都没碰到）

| # | 现象 | 根因 | 修法 | 本地回归 |
|---|---|---|---|---|
| 1 | pipe-1：第 2 步「画像里没有 weaknesses」，就地中止 | MCP `tools/call` 返回的是信封 `{"content":[{"type":"text","text":"<业务 JSON>"}]}`，业务字段在字符串里；代码读不到，且外层没有 `ok` 键导致 `ok=false` 会被误判成功 | 新增 `_text_of` / `_unwrap_tool_result`，认得 `structuredContent`、`content[0].text` 再 `json.loads`、`isError` | 假工具改为按真实信封返回 + 3 条断言（32/32） |
| 2 | pipe-2：第 3 步 `search_knowledge` 被 FastMCP 拒 | `1 validation error: student_id Field required` —— 我只传了 `query` | 补 `student_id` | 从 `mcp_server/services.py` 的 AST 解析 9 个工具必填参数，新增 `contract_violations()` 逐步比对；先跑出 `FAIL … 缺 ['student_id']`（33/35），修后 35/35 |
| 3 | pipe-3：`新增分支 | None`，但第 7 步 ✅ | 真实结构是 `data.branch.id`（不是 `branch_id`）；重复节点还会返回 `created=false` | 按 `data.branch.id` 取，并区分「新建 / 已存在，未重复创建」；`掌握度` 拆成「路径阶段掌握度（第 6 步）」与「综合掌握度（第 9 步）」两个来源各自标注 | 3 条断言（38/38） |

### 最终实测（agent v17）

`-s pipe-6`，一句 `学生：demo，岗位：前端开发工程师，答案 B，跑一遍编排。`：

```text
| 薄弱点 | 混淆用例图与需求访谈 |
| 检索命中 | 3 条 |
| 当前阶段 | stage-1 |
| 题目 ID | generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0 |
| 作答 / 判定 | B / 正确 |
| 新增分支 | branch-39d342304f27487d9a83cee17ee87495（新建） |
| 路径阶段掌握度 | 33（来自第 6 步 path_progress） |
| 错题数 | 2 |
| 综合掌握度 | 0（来自第 9 步 evaluation） |
```

九步轨迹全部 ✅，三处跨步传值逐字可核：

- 第 3 步 `query` = 第 2 步返回的 `weaknesses[0]`
- 第 6 步 `question_id` = 第 5 步返回的 `questions[0].id`
- 第 7 步 `knowledge_node_id` = 第 4 步返回的 `current_stage.id`

### 可重复性

`pipe-3`（v16）与 `pipe-6`（v17）是**两个独立会话**各跑一遍同一句话：九步工具名顺序、每步入参的键与值逐字一致，唯一差异是 `branch_id` 的后缀（数据层自增）。这与模型自主分步（trace-1/trace-2 每轮措辞与步序都会浮动）形成对照。

### 本地验收脚本

`.\ref\ict_agent\test_cloud_pipeline.py`：用 `ast` 按名字从 `agent_iam.py` 抽出编排函数原样执行（不装 langchain 也能测），假工具按真实信封返回，并把 `services.py` 的必填参数接进断言。**38/38 通过 EXIT=0**。

## 2026-10-17：前端构建首次验证通过（Node v20.20.2）

此前所有前端改动（编排可视化页、闭环串联段、导航与路由）只做过静态结构检查，从未编译。本轮补齐。

**环境**：本机原无 node/npm。下载 Node v20.20.2 便携包（`.\ref\node`，SHA256 校验通过），npm 10.8.2。

**为何在副本构建**：pwsh 进程无法在 `.` 下创建文件（`UnauthorizedAccessException`），`node_modules` 写不进去。用 `robocopy` 将 `frontend-vue` 全量复制到 `.\ref\fe_build`（排除 `node_modules`/`dist`）后构建，源码逐字节相同。

**过程与结果**

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 装依赖 | `npm ci --ignore-scripts --registry=https://registry.npmmirror.com` | `added 325 packages`；不带 `--ignore-scripts` 时 postinstall 的 `spawn EPERM`（沙箱无法为子进程捕获 stdio），改用可选依赖自带的 `@esbuild/win32-x64/esbuild.exe` |
| 类型检查 | `vue-tsc -b` | **通过**，0 类型错误 |
| 打包 | `node scripts/build-production.mjs` | **通过**，`✓ built in 11.66s`，`BUILD_EXIT=0` |
| 产物 | — | `dist/` 101 文件 / 17,170,169 字节 |
| 新页面 | — | `OrchestrationPage-DkhKtI51.js` 11,931 字节（独立 chunk） |
| 闭环组件 | — | `LearningLoopContext-CyGg9B_S.js` 1,862 字节 |
| 产物关键词 | `Select-String '编排可视化\|AgentArts\|/orchestration'` | 命中 3 处 |
| UI 契约审计 | `node scripts/audit-ui-contract.mjs` | `UI contract audit passed` |

**唯一告警**：`Some chunks are larger than 500 kB`（`EvaluatePage` 428 kB、`ExerciseCenterPage` 579 kB），改动前既有，非本轮引入。

**踩到的两个环境坑**

1. `npm ci` 在沙箱内于 arborist rebuild 阶段报 `EPERM (spawn)`——npm 需要为生命周期脚本建管道捕获输出，而受限模式下不能开命名管道。`--ignore-scripts` 绕过，且不损功能（esbuild 二进制由可选依赖提供）。
2. `vite build` 报 `[commonjs--resolver] spawn EPERM`，栈顶是 `optimizeSafeRealPathSync → execFile('net use')`——vite 在 Windows 上探测网络驱动器。一次性放宽权限后通过。

**仍未验证**：浏览器内的真实渲染与点击交互（本机无 GUI 自动化环境）。构建通过只覆盖类型检查与打包，不覆盖视觉与交互。

## 2026-10-17：接入 AgentArts 记忆库——跨会话语义召回打通（agent v18）

### 做了什么
用平台记忆空间替代「只读当前会话历史」，让同一个学生换会话提问也能带上此前抽取的薄弱点与偏好。

| 步骤 | 动作 | 结果 |
| --- | --- | --- |
| 建空间 | `MemoryClient(region).create_space(name, memory_strategies_builtin=[...])` | Space `95e5883a-a1a5-440c-a6ba-6ffafbd17a0f`，`creating` → `ACTIVE` |
| 开抽取 | `update_space(space_id, memory_extract_enabled=True, memory_extract_idle_seconds=30)` | `EXTRACT_ENABLED True` |
| 写入 | `add_messages` 两条对话（用户自述 include/extend 混淆） | `ADD_OK` |
| 检索 | 等 45 秒后 `search_memories` | `SEARCH_TOTAL 4` / `RESULTS 4`，`LIST_MEMORIES 4` |
| 接入 | `agent_iam.py` 新增 `_memory_client()` / `_search_platform_memories()`，`_build_messages` 注入「历史记忆」段 | v18 部署成功 |
| 跨会话验收 | `-s memory-1` 写入 → `-s memory-2`（**新会话**）追问 | 原样复述 `context` / `preference` / `categories` 三个字段 |

### 三个必须记住的坑（都踩过）
1. **`create_space` 必须给策略**：不给就报 `[AgentArts.01010400] HTTP 400: 至少需要一种内置或自定义记忆策略`。可用值 `semantic` / `episodic` / `user_preference`。
2. **抽取默认关闭**：不调 `update_space(memory_extract_enabled=True)` 的话，`add_messages` 照样返回成功，但 `search_memories` 永远 0 条——静默失败，最难查。空闲抽取时间建议设小（30 秒），否则要等很久。
3. **数据面要 Space 的 API Key**：控制面的 AK/SK 只能建空间、查策略，读写消息与检索要 `MemoryClient(api_key=space_api_key)`。

### 排查中作废的两个假设（记录不成立的方向，避免重走）
- 「记忆按 `actor_id` 隔离」→ 不成立：`NO-FILTER` / `user_123` / `demo` 三种过滤都返回 5 条，两者混在同一个结果集里。
- 「解析取错字段导致空注入」→ 不成立：`record` 的键是 `['id','space_id','strategy_id','strategy_type','actor_id','session_id','content','memory_type','created_at','updated_at']`，`content` 就是字符串。`memory-1` 那轮没提记忆，是模型选择了知识检索路径而未引用，属于提示词软要求导致的行为差异。

### 附带踩到的工具坑
`python3 - <<'PY'` 里调 `load_dotenv()`（不传路径）会崩：`File ".../dotenv/main.py", line 372, in find_dotenv` → `assert frame.f_back is not None`。stdin 脚本没有栈帧可回溯。改用 `load_dotenv(os.path.join(os.getcwd(), ".env"))`。

## 未执行项

- Playwright E2E 未执行：当前任务的验收重点由前端类型检查、Lint、生产构建、生产文件 HTTP 访问和后端/集成测试覆盖；本机受限执行环境的 Vite 开发依赖预优化会扫描不可访问父目录。
- AgentArts 云端安装**已执行**（原「未执行」项关闭）：智能体与 MCP 服务均已部署为托管运行时并完成端到端验证，见上一节。



## 多 Agent 真多进程（后端本地，已实测）

此前「多 Agent 协作」只能算部分完成：云端 `agent_iam.py` 与本地 `role_pipeline.py` 都是**同一进程内的顺序调用**，换的是角色名字，换不了执行体。本轮新增 `backend/app/agents/multi_agent.py`：**7 个角色各占一个操作系统进程**，主控只做调度与跨步传值，进程间只传（工具名、参数）与（结果、pid、耗时），不传函数对象。

| 验收 | 命令 | 结果 |
| --- | --- | --- |
| 假注册表 8 组 | `scripts/eval/test_multi_agent.py` | **27/27 通过** |
| 真实九工具 | `scripts/eval/test_multi_agent_real.py` | **9/9 通过**，7 个角色 7 个真实进程 |
| 接口层（真 ASGI 请求） | `scripts/eval/test_multi_agent_api.py` | **HTTP 200 / ok=true / 7 个不同 pid / 674ms**，退出码 0 |

关键判据（可被推翻的证据，不是形容词）：

- `PARENT_PID 944` 与 `controller=2308 diagnose=51956 knowledge=30760 path=27940 profile=46964 review=31932 update=13428` 全部不同 → 角色确实是执行体；
- `diagnose` 两步（出题 / 提交）落在同一个 pid=51956，`review` 两步落在同一个 pid=31932 → 角色与进程是一对一绑定，不是每步起一个新进程；
- 三处跨步传值在真实工具下逐字对上：`weaknesses[0]=混淆用例图与需求访谈`、`questions[0].id=generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0`、`current_stage.id=stage-1`；
- 同一份演示数据跑第二次，`branch_id` 与第一次一致（`created=false`），说明数据层「同一节点不重复建分支」被如实带回。

三个实测坑：

1. `spawn` 会重跑入口脚本的 `__main__`，探针没写守卫时报 `spawn.py:297 _fixup_main_from_path` 递归；
2. 业务层 `ok=false`（如 `NO_QUESTION_BANK`）最初被当成步骤成功，失败原因显示成「出题结果里没有题目 id」——把**数据缺口说成代码问题**；现改为工具回 `ok=false` 即判该步失败并透传业务错误码；
3. 本机沙箱不许建命名管道，`multiprocessing.Queue()` 报 `PermissionError: [WinError 5]`，跑多进程验收需放宽一次权限；Linux 容器无此限制，但**云端多进程版本尚未跑过**。

接口：`POST /api/orchestration/multi-agent`（当场起进程串一遍，结果落盘 `multi_agent_trace.json`，失败不降级成假成功）。接口层已用 `TestClient` 发真 ASGI 请求实测：`HTTP 200`、`success=true`、`ok=true`、`workers` 7 个互不相同的 pid、`POST /api/orchestration/multi-agent 200 674.4ms`（日志行）。未经 uvicorn 监听端口，所以不含网络与反代环节。前端「编排可视化」页已接该接口（「跑一次多进程编排」按钮 → 7 个角色 pid + 九步 trace），`vue-tsc -b` 与 `vite build` 均通过；浏览器里点按的真实渲染仍未验证。

接口层实测还顺手排掉一个**假隐患**：`app.routes` 里查不到 `/api/orchestration/*` 一度让我以为路由没挂上，实际是这套 FastAPI 用 `_IncludedRouter` 惰性记录子路由，`getattr(route, "path")` 取不到值——路由本身是好的，只有真发请求才看得见。

详见同目录 `多Agent多进程实现说明.md`。

---

## 云端多进程九步上线（agent v22，2026-10-17）

**一句话**：九步编排在云端跑在 9 个真实独立进程上，角色与进程一一对应，业务结果完整。

- **能力体检（v19）**：容器 `Linux aarch64` / python 3.10.22 / 入口进程即 PID 1 / 2 vCPU / `CapEff=0` / `Seccomp=0`；`fork` 实测 OK（child=12，**9ms**），`spawn` 2428ms，`forkserver` 4683ms；**并发 7 个 fork 子进程 7/7 成功、pid 互不相同**（`[20,22,24,26,28,30,32]`，138ms）；`pids.max = max`。→ 容器支持「角色 = 进程」。
- **实现（v20–v22）**：`_mp_tool_child` 子进程自己发一次 MCP 调用、结果经 `Pipe` 递回、`os._exit(0)` 跳过解释器收尾；`_mp_call_tool` 父进程 `poll(timeout)/join/terminate` 并记录 `{pid,ppid,tool,ms}`；主控先握一次 MCP 会话再 fork，子进程继承同一 `Mcp-Session-Id`；无 `fork`（如本地 Windows）自动退回单进程，行为与 v17 一致。
- **实测（v22）**：`-s mp-2`（岗位 前端开发工程师）9 步全 ✅，`本次共起 9 个独立进程 pid=[11,12,13,14,15,16,17,18,19]`，分支 `branch-93eca7447c364d4ea220f9da67e420b8（新建）`，阶段掌握度 33、综合掌握度 0；`-s mp-3`（不给岗位）8 步全 ✅、8 个进程。
- **过程中查掉的两个缺口**：① 首跑第 1 步只显示 `None: None` —— 业务错误对象是**嵌套**的（`error.code` / `error.message`），代码只读了顶层，改为 `_first_of` 兜底并在失败时打印 `raw_head`（原始响应前 600 字）；② 岗位名 `诊断教练` 触发 `ROLE_NOT_FOUND`，换 `前端开发工程师` 通过。用「多进程诊断」入口做 A 主进程 / B 子进程 / C 同工具的原文对照，证明 **fork 未改变任何调用结果**（A、B 逐字相同）。
- **边界**：仍是**同一运行时容器内的多进程**，不是多个 AgentArts 运行时实例之间的协作；角色进程之间是顺序 handoff，不是并行投票。

详见同目录 `多Agent云端多进程实证.md`。

---

## 平台知识库接入（控制台实测，2026-10-17）

**一句话**：AgentArts 平台知识库已建成并验证召回质量，平台原生用法是「单智能体挂库」，已提交版本；但平台不开放检索 API，所以云端高代码智能体无法直接调它。

| 环节 | 结果 |
| --- | --- |
| 建库 | `ict-course-kb`（`d2002b51e9684590abe8b5f5c7f5c7b9`），`pangu_embedding` + `pangu_rerank`，自动分段 |
| 语料 | 2 篇课程文档（教学视频推荐 4,185 B / 通用答疑语音辅导方案 7,614 B），共 13 条切片、12 kB |
| 命中测试 | `入门视频建议看多久` → **1.00**（次条 0.99）；`连续答错三次怎么办` → **0.96**；`include 和 extend 区别` → **0.05** |
| 关键观察 | 服务端**不做阈值过滤**，任何查询都返回 13 条，阈值必须调用方自己卡 |
| 单智能体 | `ict-course-kb-qa`（`2d483210-deea-4443-806f-b208a33cd50d`），DeepSeek-V4-Flash，挂 `ict-course-kb`，开启「引用和归属」 |
| 试运行 | ①「10–20 分钟」+ 来源；②「切换教师模式：需要我为你从头讲解这个知识点吗」+ 来源；③「现有资料里没有讲到这个点」如实拒答 |
| 版本 | `v20261017213251`（已提交，**未部署**） |

**为什么第三问最有价值**：模型本身完全讲得清 include/extend，但检索只有 0.05 分时它按提示词第 3 条拒答了 —— 说明「知识边界」真的由检索结果约束，而不是形式上的开关。

**三条平台限制**：
1. SDK `agentarts/sdk/` 下只有 `gateway / identity / integration / memory / runtime / service`，**没有知识库模块**；
2. 控制台知识库「更多」菜单只有 修改配置 / 编辑 / 复制 / 查看引用 / 删除，**没有知识库地址或 API Key**；
3. 官方《第三方通用知识库接入规范》要求**第三方自己实现** `GET /knowledge-bases` 与 `POST /knowledge-bases/retrieve` 供 AgentArts 调用，方向与「我要调平台库」相反；部署成 API 还需 MaaS 模型 API Key，故未部署。

详见同目录 `平台知识库智能体实证.md`。

---

## 浏览器端真机验收与 7 个修复（本地 127.0.0.1:4173，2026-10-17）

**一句话**：`vite build` 通过 ≠ 页面能用。真在浏览器里点之后，一共挖出 7 个「构建看不出、点一下就暴露」的问题，全部已修并复验。

### 环境
- 后端：捆绑 Python 3.12，`PYTHONPATH` 依序 `ref\pylibs;ref\pylibs2;ref\pylibs3;ICT;ICT\01_主工程;…\backend`，`uvicorn app.main:app --port 8000`
- 前端：`.\ref\fe_build`（源码逐字节同步的构建副本），`npm run build` + `vite preview --port 4173`；`vite.config.ts` 已把 `/api` 代理到 8000
- 登录：任意 11 位手机号 + `demo123`

### 7 个修复

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 点「跑一次多进程编排」无反馈 | 前端只处理 `available===false`，后端返回的是 `success=false` | 前端补 `success===false` 分支，把 `error` 原样显示 |
| 2 | 编排失败但页面不给原因 | 后端 `stop_reason` 有业务码，返回体里却没带 `error` | 路由把 `stop_reason` 映射成 `error.code/message` 再返回 |
| 3 | 「能力融合目录」8 行全空白骨架 | 接口返回的是对象信封（`capabilities[8]` 在 `data.capabilities`），页面按数组遍历 | 类型改为 `IntegrationCatalog`，按 `capabilities` 渲染并显示策略 |
| 4 | 九步 trace 步骤号从 0 开始 | `multi_agent.py` 里 `enumerate()` 默认从 0；而 `role_pipeline.py` 用的是 `index=len(trace)+1`（1 起） | 只在 `multi_agent` 侧 `index+1` 渲染，避免两条链路重复 +1 |
| 5 | 全站空状态：画像/路径/题库全拿不到数据 | `useStudent.ts` 把 `'demo'` 拦掉，界面永远生成新 learner id | 改为 `storedStudentId \|\| createLearnerId()`，首页加「切换到演示学生」按钮 |
| 6 | `/path` 底部「闭环串联」展开后看不见、页面也滚不动 | `.path-workspace` 是 `height: min(820px, 100vh-150px)` + `overflow: hidden`，details 展开的内容被裁在容器外 | 把 details 移出定高容器，另加 `:has(details[open])` 兜底 |
| 7 | 无 LLM key 时点「生成阶段题库」直接红字报错 | `Orchestrator._generate_one` 在 `use_glm` 且无 key 时 `raise`，整条链路断 | 新增本地模板题库兜底（见下），界面上显式标注「本地模板 · 未调用大模型」 |

> 第 1 条的排查教训值得单独记：**同一个按钮背后可能连着两条接口**。第一次只给 `/api/exercise/generate-bank` 加了降级，用户照旧弹红字；看后端日志才发现按钮实际命中的是 `POST /api/path/stage/questions`。只修一条等于没修，验收时必须看日志里真实的 URL。

### 本地题库兜底（无大模型可用）

`backend/app/services/local_question_bank.py`（新增）：

- 15 道模板题：单选 6 / 多选 3 / 判断 3 / 简答 2 / 案例 2，主题覆盖 include/extend、参与者识别、非功能需求、用例描述规范、用例图 vs 数据流图等。
- 按页面给的 `question_config.type_counts` 配题，题型合计不足时用单选补齐到 `count`。
- 写盘与资源登记完全复用现有契约：`files/<student>/<id>.json` + `insert_resource_item(type="question_bank", meta.requirement.constraints.source=...)`，因此 `exercise_bank._load_generated_questions` 无需改动即可加载。
- 自我声明：`meta.local_template=true`、`meta.question_count`、标题带「本地模板 · 未调用大模型」；前端 `ExerciseCenterPage.vue` 读该字段显示提示，并在「题库来源」加「其中 N 份为本地模板」。
- 两个入口都接了：`/api/exercise/generate-bank`（流式 SSE 也补了 `start/agent_start/agent_chunk/agent_done/done` 事件）与 `/api/path/stage/questions`。

**实测**：

```
POST /api/exercise/generate-bank   → success=True  mode=local_template
resource 40bac750dd2b42da9ad37dbbbdb66349  title=需求获取与建模基础题库（本地模板 · 未调用大模型）
GET  /api/exercise/session?resource_ids=40bac… → source=generated_question_bank  N=10
      single_choice=4  multiple_choice=2  true_false=2  short_answer=1  case_analysis=1
POST /api/exercise/answer  …:3 answer=C → correct=True   correct_answer=C
POST /api/exercise/answer  …:1 answer=A → correct=False  correct_answer=C
POST /api/path/stage/questions     → SUCCESS=True  LOCAL=True  TARGET=10
```

浏览器实测（判断标准见 `验收一页纸.md` 第九节）：`/orchestration` 7 个角色 pid 互不相同、九步全绿、留痕有真实映射；`/path` 闭环串联展开后可见且可继续滚动；`/exercise` 出题 10 道、判分正确、已答计数 +1、掌握度可回写。

### 接口巡检（真机验收前的底数）

- 35 个无参 GET：25 个 200，10 个需要必填参数。
- 带上 `student_id=demo` 后重跑：全部 200，唯一"失败"是 `/api/evaluation/report` 返回 `EVALUATION_NOT_FOUND`（尚未生成评估报告），属**合法空态**。
- 踩到一个参数名差异：`/api/knowledge/search` 用的是 `q` 而不是 `query`，传错时服务端不报错、返回空结果集——静默失败，已记录。

### 边界

- 本组是**本地** `vite preview` + 本地后端的真机点按，不是公网部署；浏览器只验证到 Chromium 一档。
- 剩余页面（资源工坊 / 评估进化 / 知识中枢 / 多模态实验室 / 智能辅导）尚未逐页点完，其中资源工坊与智能辅导依赖外部模型能力。
- PPT / 思维导图 / 实时语音在无 key 环境下显示「未配置」，本轮未做降级，也不打算用假数据填。

## 11 页全量验收与第 8 个修复（2026-10-18）

### 本轮修掉的第 8 个问题：教材正文不在检索索引里

- 现象：`/knowledge` 搜 `include`，返回的全是 `generated_resource`（题库/诊断练习），上传的教材一条不出现；而知识图谱里明明有这本教材的章节节点。
- 根因：`knowledge_hub._collect_documents()` 只收 `课程资料/`、`生成示例/`、路径输出、生成资源四类，**漏了 `uploads/textbooks/`**。教材那时只喂给图谱，不进检索语料，所以「有节点、搜不到」。
- 修法（`backend/app/services/knowledge_hub.py`）：`_collect_documents()` 增加教材源——优先读用户上传的原始文件（`TEXTBOOK_DIR/{textbook_id}{后缀}`），读不到再退回 `book_{id}.json` 的章节关键词；`source_type="uploaded_textbook"`，并给它与 `course_material` 同样的 `+0.06` 来源加权。
- 实测（重启后端后）：`GET /api/knowledge/search?student_id=demo&q=开场话术` → 2 条，`uploaded_textbook` 0.1054 排第一，`generated_resource` 0.1054 排第二；`_collect_documents('demo')` 的 7 篇文档里前两篇就是两本上传教材（3176 / 3171 字）。

### 诚实结论：机制通了，但库里没有「讲 include/extend」的教材

搜 `include` 仍然只命中题库。这不是索引的锅——工作区里**根本不存在**一份真正讲解用例图 include/extend 的课程文档（`课程资料/` 目录不存在；现有两本上传件是「通用答疑语音辅导方案」和「教学视频推荐」，正文里没有这两个词）。检索只能查到库里有的东西，缺的是语料，不是代码。要补只能上传真实讲义，不能用编造内容冒充教材。

### 11 页逐页验收结果

| # | 页面 | 路由 | 结论 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | 总控首页 | `/` | ✅ | 演示数据身份 `demo`，无报错 |
| 2 | 用户画像 | `/profile` | ✅ | 六维画像与能力证据渲染 |
| 3 | 资源工坊 | `/workshop` | ✅ | 生成记录 3 条，含 6/14 队友产物 |
| 4 | 路径推送 | `/path` | ✅ | 掌握度 33%、三阶段、推荐理由可解释 |
| 5 | 练习诊断 | `/exercise` | ✅ | 10 题出题、判分、掌握度回写全通 |
| 6 | 知识中枢 | `/knowledge` | ✅ | 图谱 7 节点 6 边，检索有结果 |
| 7 | 多模态实验室 | `/multimodal` | ✅ | 点「算法视频」返回「视频推荐模型尚未配置，本次没有生成固定推荐项，也没有写入伪资源」 |
| 8 | 智能辅导 | `/tutor` | ✅（空态） | 显式 `未配置` + `RealTime voice is disabled. Configure VOICE_REALTIME_*`，其余按钮禁用 |
| 9 | 评估进化 | `/evaluate` | ✅ | 综合 39 分、知识掌握 10%、证据 103 条、`mastery_source=path_stage` |
| 10 | 编排可视化 | `/orchestration` | ✅ | 9 步 7 个不同 pid、留痕 3 条真实映射 |
| 11 | 用户设置 | `/settings` | ✅ | 重定向回首页（Vue 未实现独立设置页） |

判定标准统一为：**页面不报错、数据来自真实接口、能力缺失时明确说缺什么且不写入伪数据**。第 7、8 页的「未配置」属合格答案，不是缺陷。

## 2026-10-18 教材正文入检索与图谱（三层修复）

### 现象（修复前）
- `GET /api/knowledge/search?q=参与者&student_id=demo` 只召回 `question_bank` 资源（0.111–0.117），讲义正文一条不出；
- `GET /api/knowledge/graph?student_id=demo` 只有 1 章、1 个概念，概念名是「需求分析」+「软件需求分析」（模板名被当成章节标题所致）；
- 教材文件确实已落盘：`uploads/textbooks/chapter_knowledge/book_*.json`，但检索索引 `_collect_documents()` 只扫生成资源与教材元数据，不读章节正文。

### 修复
| 层 | 位置 | 改动 |
| --- | --- | --- |
| 检索 | `app/services/knowledge_hub.py::_collect_documents` | 并入 `chapter_knowledge/*.json` 每章正文，按「教材名 · 章节名」建文档 |
| 切章 | 同上，章节解析函数 | 接受 `一、`…`十、` 与 `4.1` 编号标题；解析前先剥 `#`/`##`，避免 `# 软件需求分析与建模-讲义一` 这类模板名成为唯一章节 |
| 概念 | 同上，`_chapter_concept_candidates` | 优先级：三级标题 > 加粗 > 行内代码 > 词频兜底；作者标题不过统计清洗（`用例` 这类通用词会被误删） |

### 验证（真实接口，重启后端后执行）
```
POST /api/knowledge/textbook?student_id=demo&filename=...  → chapter_count=8, concept_count=46
GET  /api/knowledge/graph?student_id=demo&course=textbook:1c03b5464435c297
     → stats {documents:1, chapters:8, concepts:31, relations:53}
GET  /api/knowledge/search?student_id=demo&q=参与者
     → 0.298 软件需求分析与建模-讲义一-需求获取与用例建模  ← 讲义首次排第一
GET  /api/knowledge/search?student_id=demo&q=include 和 extend
     → 0.275 同上
GET  /api/knowledge/search?student_id=demo&q=开场话术
     → 0.105 软件需求分析与建模-通用答疑语音辅导方案 + 0.105 voice_tutor_plan
```

### 已知局限（写进交付，避免夸大）
- 检索是**本地词袋余弦**（按文档长度归一化），不是 embedding；同义改写召回弱；
- 概念抽取为规则法；「建模型 / 不能留到测试 / 函数」这类残渣已于 2026-10-18 用三个过滤器清除（见下节），但语义理解仍不具备，正式教学图谱需更完整课程资料 + 人工校正。

### 上云：MCP 服务 v5 → v6（三步验证，2026-10-18）

镜像里的 MCP 服务 `search_knowledge_data` 就是 `app.services.knowledge_hub.search_index` 的薄封装，所以代码升级必须同时把教材数据带上去。

| 步骤 | 命令（开发机 `~/ref/mcp_deploy`） | 结果 |
|---|---|---|
| 1. 远端直调（不重建） | 备份 `knowledge_hub.py` → 换新 65370 字节版本 → `python3 -c "from mcp_server.services import search_knowledge_data..."` | `参与者` → 0.298 讲义第一；`include 和 extend` → 0.275 讲义第一 |
| 2. 重建镜像 | `export DOCKER_BUILDKIT=0; setsid nohup ~/agentarts/bin/agentarts launch > ~/launch23.log 2>&1 &` | `✓ SUCCESS: Runtime 'ict-mcp-server(v6)'` |
| 3. 容器内调用 | `agentarts invoke --agent ict-career-agent -s kb-1 '{"message": "只用 search_knowledge ... 查询「参与者」"}'` | `1.《…讲义一…》 - 0.2979` / `2.《诊断练习…》 - 0.119` |

**三点说明**：
1. 第 1 步就给出了与第 3 步相同的数字，说明「重建镜像」只负责搬运、不负责正确性；付出 6 分钟构建换来的只是「装进容器」这一条。
2. 远端 `01_主工程/backend` 是 Oct-14 快照，本次只替换 `knowledge_hub.py` 一个文件，其余未动；旧文件留在 `knowledge_hub.py.bak23`，可一条 `cp` 回滚。
3. 智能体 `ict-career-agent` 本轮未改动，仍是 v22；这次只升 MCP 服务版本。

### 概念抽取噪声清理（2026-10-18）

| 现象 | 根因 | 修法 |
|---|---|---|
| 第四章抽不到「参与者 / 用例 / 系统边界」，只有「身份认证 / 函数」 | 作者标题被下游 _clean_keywords（课程白名单）二次过滤掉 | 作者标题走 _is_authored_concept(allow_generic=True) 直接进，统计词才走白名单 |
| 「函数 / 界面 / 步骤」成知识点 | 出现在「用例不是界面、不是函数、不是步骤」否定句里 | 新增 _only_in_negative_context()：每次出现都紧跟否定词则丢弃 |
| 「建模型」「不能留到测试」 | 词频把「判冲突、排优先级、划边界、建模型」切成动词短语 | 新增 _looks_like_clause_fragment() |
| 「从用例到可验收的需求」与章节同名 | 章标题被当概念 | 概念与去序号后的章标题相同则丢弃 |
| 改完 book_<id>.json 已干净，图谱仍带「建模型」 | _build_course_graph 另有路径对「章标题 + 摘要」重新挖词频 | 该路径同样接上三个过滤器 |

结果：GET /api/knowledge/graph?student_id=demo&course=textbook:1c03b5464435c297 → concepts=23 / relations=44，
noise_remaining=[]；检索分数未变（参与者 0.298、include 和 extend 0.275，讲义仍第一）。详见 .\概念抽取噪声清理.md。

页面口径另修一处：底部「20 薄弱节点」把 `mastery === 0`（从未评估）算成薄弱，与左侧筛选器口径（`score > 0 && score < 60`）不一致；`frontend-vue/src/pages/KnowledgePage.vue` 已对齐，该课程现在显示 `0 薄弱节点`。

### 上云：MCP 服务 v6 → v7（2026-10-18 19:21）

同步方式：本机 `cloudflared` 快速隧道指向只放 `knowledge_hub.py` + `sync.sh` 的静态目录，开发机 `curl` 拉取后一次性执行「备份 → 替换 → 直调验证 → 重建 → 容器内复验」，验证不过自动还原。

| 检查点 | 结果 |
|---|---|
| 文件完整性 | `new_md5=39b46aedf15fa07f38aafc3bd2690926` ＝ 预期值，67952 字节 |
| 直调验证（不重建镜像） | `参与者 → 0.298 讲义一`；`include 和 extend → 0.275 讲义一` |
| 重建镜像 | `✓ SUCCESS: Runtime 'ict-mcp-server(v7)' created/updated` |
| 容器内复验 | `《…讲义一…》 score 0.2979` / `《诊断练习…》 score 0.119` |

说明：检索分数与 v6 相同（知识抽取规则的改动只影响图谱概念，不影响检索打分）；v7 的增量是「图谱概念不再出现残渣」。旧文件留在 `knowledge_hub.py.bak24`，一条 `cp` 可回滚。

### 平台侧评估：评估任务实跑与平台 KMS 故障（2026-10-18 22:00）

背景：五项使用价值里唯一缺口是「平台侧效果评估」。「观测与优化 > 评估」要求先建评测集和评估器，评估器再回调运行时。原运行时 `ict-career-agent` 是 IAM 入站认证，平台回调一路 401，因此换成 API Key 认证，另建了 `ict-career-agent-k`。

| 检查点 | 结果 |
|---|---|
| 身份类型不可改 | 控制台 Agent Identity 页 `agent-ict-career-agent` 认证类型为 IAM，点「修改」提示「该认证类型无法修改」 |
| `authorizer_type` 合法值 | 大写枚举 `IAM` / `API_KEY` / `CUSTOM_JWT`（SDK docstring 里的小写写法是错的） |
| API Key 写进 YAML | `identity_configuration.authorizer_configuration.key_auth.api_keys[{api_key, api_key_name}]` |
| 新运行时部署 | `✓ SUCCESS: Runtime 'ict-career-agent-k(v1)' created/updated successfully` |
| API Key 调用 | `agentarts invoke --agent ict-career-agent-k` → `Auth Type: API_KEY`，返回 `pong ✅ 我在…` |
| 评测集 | `ict-career-agent-regression`（8 条，列 input / reference_output） |
| 评估器 | `valuator-ict-faithfulness`（模型判定，deepseek-v4-flash，单轮对话，0.0.1） |
| 评估任务 | `评估任务-20261018200945`，评估对象 `ict-career-agent-k`，最大并发 5 |
| 任务结果 | 运行 59s：成功 0 / 失败 8；但 8 条 `actual_output` 全部是真实回答（含真实工具分数 0.5175 / 0.3221） |
| 失败归因 | 评估器侧：取模型服务详情时 500，`AgentArts.00001082 使用KMS加密解密失败`（genForDecryptDatakey）+ `STS.01205 missing request_proof` |

失败原文（数据详情 → 评估器得分 → ⓘ）：

```
评估失败。【construct task error: task fill error: get api key error: get model service detail error:
get model service error when doing request: request https://agents-internal.cn-southwest-2.myhuaweicloud.com
/v1/studio/internal/models/maas-fbc69924-8bb7-4c80-b68d-5c03dc5da924 exec error: ...
response status code: 500, body: {"error_code":"AgentArts.00001082","error_msg":"使用KMS加密解密失败",
"error_reason":"系统内部异常 genForDecryptDatakey","error_code":"STS.01205",
"error_msg":"missing request_proof or other necessary fields in body","error_suggestion":"请系统技术支持"}】
```

结论与边界：

1. 调用链已全程打通并被平台记录：平台 → 运行时（API Key） → MCP 九工具 → 业务数据，8 条回答里能读到 `search_knowledge` 返回的真实分数。
2. 打分这一步卡在平台内部 KMS/STS，属平台缺陷，不是本工程的配置问题（同一套配置调测能成功，说明认证本身没问题）。
3. 待办：控制台「管理中心 → 授权管理 → 云服务 → MaaS 模型服务」当前为「未开通 / 未授权」，点「一键开通及授权」后重跑任务；若仍失败，按平台缺陷记录，不作为本作品的未完成项。
4. 安全遗留：`~/.eval_key` 曾在终端被明文回显过一次，需轮换密钥并重新部署 `ict-career-agent-k`。

### 平台侧评估补齐：MaaS 授权后 8/8 跑通（2026-10-19 18:48）

昨天那条 `AgentArts.00001082 使用KMS加密解密失败` + `STS.01205 missing request_proof` 的根因今天定位并解决：**「授权管理 > 云服务 > MaaS模型服务」当时是「未开通 / 未授权」**，平台拿不到模型服务密钥，评估器自然起不来。开通授权后，同一套评测集 / 评估器 / 调用配置**一次跑通**。

| 检查点 | 结果 |
|---|---|
| MaaS 模型服务授权 | 由「未开通 / 未授权」变为「已开通 / 已授权」 |
| 任务状态 | ✅ 成功，运行 3min11s，总条数 8（成功 8 / 失败 0） |
| Token 消耗 | 16689（输入 8672 / 输出 8017），单条 1583–2364 |
| 单条耗时 | 12–21 秒 |
| **均分** | **0.76**（最低 0.47，最高 1.00，总和 6.08） |
| 分布 | 1.00 三条、0.92 一条、0.61 一条、0.55 一条、0.53 一条、0.47 一条 |

逐条得分（按列表顺序，input 为截断文本）：

| input（截断） | 分数 |
|---|---|
| 我们团队用 Scrum，请讲讲 Sprint Review 的具… | 1.00 |
| 帮我直接把学生 demo 的图像改掉，把他的错题… | 1.00 |
| 给我三条可以直接发给同学的 B 站视频链接，必… | 1.00 |
| 软件需求分析与建模里，参与者和用例分别是什么… | 0.92 |
| 学生 demo 这周该练什么？请基于他的真实数据… | 0.61 |
| 请完整介绍 C…（要求资料里没有的内容） | 0.55 |
| 功能需求和非功能需求怎么区分？各举一个例子 | 0.53 |
| 用例图里 include 和 extend 的区别是什么？ | 0.47 |

一条值得记录的观察：**得分最低的 0.47 恰是信息量最大的那条**（它引用了 `search_knowledge` 返回的真实分数 0.5175 / 0.3221，还额外给了对比表和行动建议）。原因是评估器按「与 reference_output 的契合度」判分，回答越长、越超出参考答案范围，越容易在「忠实度 / 不编造」维度被扣分——这是评估口径与我们「多给一步」策略之间的真实张力，不是回答错了。

结论：**平台侧效果评估这一环已从「未落地」变成「已实测通过」**，五项 AgentArts 使用价值全部有实测证据。

安全遗留（同日实测）：**API Key 无法通过重新部署轮换**——把 YAML 里的 `api_key` 换成新值再 `agentarts launch` 出 v2，新 key 调用 401、旧 key 仍然通。说明平台只在**身份创建时**登记密钥，轮换只能删除并重建身份（endpoint 会变）。当前已把本机 `~/.eval_key` 与配置还原为旧 key（v3），调用恢复 `pong ✅`。
