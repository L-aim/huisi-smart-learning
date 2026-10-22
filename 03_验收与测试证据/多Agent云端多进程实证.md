# 多 Agent 云端多进程实证（v22，2026-10-17）

一句话：**九步编排在云端跑在 9 个真实独立进程上，角色与进程一一对应，业务结果完整。**

此前「多 Agent 协作」只能算部分完成——单 Agent 内按角色顺序编排，SDK 里检索 `handoff|subagent|multi-agent` 零命中，平台没有多智能体原语。本页记录把它做成真进程的全过程与证据。

---

## 一、先证明容器能不能 fork（v19 体检）

在云端运行时里加了一个只认「多进程体检」四字的直通入口（绕开模型、不调 LLM），输出容器事实：

| 项 | 实测值 |
| --- | --- |
| platform | `Linux-6.6.0-72.0.0.76.r1014_62.hce3.aarch64-aarch64-with-glibc2.41` |
| python | 3.10.22，`/usr/local/bin/python` |
| PID | `os.getpid() = 1`（入口进程就是容器 PID 1） |
| CPU | `cpu_count = 2`，`Cpus_allowed_list = 0-1` |
| start_methods | `['fork', 'spawn', 'forkserver']`，当前 `fork` |
| CapEff | `0000000000000000`（无 capability，fork 不需要） |
| Seccomp | `0`（未启用过滤） |
| `/sys/fs/cgroup/pids/pids.max` | `max`（cgroup v2 文件不存在，v1 路径可读） |
| **fork 实测** | **OK**，parent=1 child=12，**9ms**，exit=1 |
| forkserver 实测 | OK，child=16 ppid=15，4683ms |
| spawn 实测 | OK，child=18，2428ms |
| **并发 7 个 fork 子进程** | **OK 7/7，distinct_pids=7**，`[20,22,24,26,28,30,32]`，138ms |

结论：容器允许 fork、允许建管道、进程数不受限。**「角色 = 进程」在云上做得成。**

一个要注意的细节：`Queue` 版 fork 子进程 **退出码是 1**（spawn/forkserver 是 0）。子进程已经把数据递回来了，但解释器收尾阶段有异常污染了退出码。修法在实现里：子进程把结果写完就 `os._exit(0)`，跳过解释器收尾。

## 二、把工具调用搬进子进程（v20–v22）

`.\ref\ict_agent\agent_iam.py` 改动：

1. `_mp_tool_child(conn, tool, arguments)`：子进程自己发一次 `call_mcp_tool`，结果用 `Pipe` 递回，然后 `os._exit(0)`。
2. `_mp_call_tool(tool, arguments, pid_sink)`：父进程侧建 `Pipe(duplex=False)`、`ctx.Process(daemon=True)`、`poll(timeout)` 收结果、`join(5)`、必要时 `terminate()`；把 `{pid, ppid, tool, ms}` 记进 `pid_sink`。
3. `_mp_supported()`：`MP_PIPELINE=0` 或环境没有 `fork` 时返回 False → **自动退回单进程**，行为与 v17 完全一致（本地 Windows 走的就是这条）。
4. `TravelAgent._run_role_pipeline`：多进程时先由**主控进程握一次 MCP 会话**，子进程 fork 后继承同一个 `Mcp-Session-Id`，否则每步子进程各建一个会话，写入类工具的结果下一步读不到。
5. `format_pipeline_result`：结果表新增「执行方式」「进程」两行，写出进程数与 pid 列表。

## 三、云端实测（v22，两条会话）

会话 `mp-2`（岗位 `前端开发工程师`，答案 B）：

```
## 结论
确定性九步编排执行完毕：学生 `demo`、岗位 `前端开发工程师`，共 9 步全部成功。
| 新增分支 | branch-93eca7447c364d4ea220f9da67e420b8（新建） |
| 路径阶段掌握度 | 33（来自第 6 步 path_progress） |
| 综合掌握度 | 0（来自第 9 步 evaluation） |
| 执行方式 | 多进程（角色=进程） |
| 进程 | 本次共起 **9** 个独立进程，pid=[11,12,13,14,15,16,17,18,19]（主控 pid 之外互不相同；每个进程自己发一次 MCP 调用） |
```

会话 `mp-3`（未指定岗位，第 0 步按设计跳过）：

```
共 8 步全部成功
| 新增分支 | branch-6fcec86d8cb9b4c92910bd71ab78e4de9（新建） |
| 进程 | 本次共起 **8** 个独立进程，pid=[11,12,13,14,15,16,17,18] |
```

九步的工具名顺序、每步入参、跨步传值（薄弱点→检索词、阶段 ID→知识节点、题目 ID→提交）与 v17 单进程版逐字一致——变的只有执行载体，不是业务逻辑。

## 四、中途那个「第 1 步 None: None」是怎么查掉的

v20 首次跑多进程，第 1 步 `get_role_competency` 失败，错误渲染成 `None: None`。没有猜，加了「多进程诊断」入口做三段对照：

- **A 主进程**直接调 `get_student_profile` → raw `ok: true`，5293 字符
- **B 子进程**（fork + Pipe）调同一个 → pid=11 ppid=1 239ms，raw 与 A **一致**
- **C 子进程**调 `get_role_competency {"role_name": "诊断教练"}` → pid=12 140ms，raw：

```json
{"ok": false, "data": null, "error": {"code": "ROLE_NOT_FOUND", "message": "未在结构化岗位画像中找到对应岗位。"}}
```

两个结论，都不是多进程的错：

1. **fork 没有改变任何调用结果**（A 与 B 逐字相同），多进程方案本身没问题；
2. 真实原因有两个——① 岗位名 `诊断教练` 不在结构化岗位画像里；② **业务失败的错误对象是嵌套的**（`error.code` / `error.message`），我只读了顶层 `code`/`message`，所以渲染成 `None: None`。

修法：错误解析改为 `payload.get("code") or _first_of(payload, "code")`，并在 `ROLE_NOT_FOUND` 时直接给出提示；失败步骤额外打印 `raw_head`（原始响应前 600 字），让下一次失败自带证据。换 `前端开发工程师` 后九步全通。

有效岗位名实测：`前端开发工程师` ✅；`诊断教练` ❌（ROLE_NOT_FOUND）。不给岗位则第 0 步跳过、跑 8 步。

## 五、复现命令（云终端）

```bash
source ~/agentarts/bin/activate && cd ~/ref/code_new
curl -fsSL https://scheduled-meal-compiled-inspections.trycloudflare.com/ict_agent/agent_iam.py -o agent.py
python3 -c "import ast;ast.parse(open('agent.py',encoding='utf-8').read());print('SYNTAX-OK')"
export DOCKER_BUILDKIT=0; setsid nohup ~/agentarts/bin/agentarts launch > ~/launch22.log 2>&1 < /dev/null &
for i in $(seq 1 14); do sleep 30; grep -qE 'Deployment complete|ERROR' ~/launch22.log && break; done; grep -E 'SUCCESS|ERROR' ~/launch22.log | tail -n 3
~/agentarts/bin/agentarts invoke --agent ict-career-agent -s mp-2 '{"message": "学生 demo 走确定性九步编排，岗位 前端开发工程师，答案 B"}'
```

体检入口：`{"message": "多进程体检"}`；对照诊断入口：`{"message": "多进程诊断"}`。

## 六、边界（不要过度宣称）

- 这是**同一运行时容器内的多进程**，不是多个 AgentArts 运行时/智能体实例之间的协作；平台侧仍是一个 Agent。
- 角色进程之间是**顺序 handoff**（上一步的输出作为下一步的入参），不是并行竞争/投票。
- 主控进程 + 子进程共享同一容器（2 vCPU / 内存受限），单次九步耗时主要由 MCP 调用决定（每步几十到几百 ms）。
- 子进程崩溃、超时（默认 90s，`MP_TOOL_TIMEOUT` 可调）都会如实中止并记录，不补写结果。
- 本地 Windows 没有 `fork`，走的是单进程回退路径；本地多进程证据在 `test_multi_agent.py`（24/24，7 个真实 PID）与 `test_multi_agent_real.py`（9/9，真工具）里，用的是 `spawn`。
