from __future__ import annotations

import os
from typing import Any, Optional, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.services import (
    add_learning_branch_data,
    get_exercise_session_data,
    get_learning_evaluation_data,
    get_project_status_data,
    get_role_competency_data,
    get_student_profile_data,
    get_wrong_book_data,
    search_knowledge_data,
    submit_exercise_answer_data,
)


HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8010"))


class ToolEnvelope(TypedDict):
    ok: bool
    data: dict[str, Any] | None
    error: dict[str, Any] | None
    meta: dict[str, Any]

mcp = FastMCP(
    "ict-agentarts-tools",
    instructions="为 AgentArts 提供学生画像、岗位能力和学习项目状态查询。",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=False,
    # 说明（2026-10-20）：FastMCP 1.30 默认开启 DNS rebinding 防护，只比对
    # Host 头与 allowed_hosts 的「精确值」或「basehost:*」两种形式，不支持
    # *.example.com 这类子域通配。本服务是要被 AgentArts 网关从公网拉取的
    # （经 Cloudflare 快速隧道，域名每次启动都随机），任何固定白名单都匹配
    # 不上，实测表现为 Target 一直「离线」、直连 /mcp 返回 421 Misdirected
    # Request。因此这里关闭该防护：它是给本机开发服务防浏览器 DNS 重绑定用
    # 的，对「故意对外暴露的随机域名」没有防护价值；访问控制由服务自身的
    # API Key 校验与限流（MCP_API_KEY / rate_limit_per_min）承担。
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=["*"],
    ),
)


# 说明（2026-10-13）：以下三个工具刻意不写返回类型注解。
# 写了 `-> ToolEnvelope` 时 FastMCP 会为每个工具生成 outputSchema，
# 而 AgentArts 网关的 MCP 实现不支持 outputSchema（官方文档明确写
# “tools/list 不回传 outputSchema”），会导致网关侧工具列表解析为空。
# 不写注解后返回值会以 JSON 文本放进 content[0].text，网关可正常中继。
@mcp.tool()
def get_student_profile(student_id: str):
    """按学生 ID 查询基础信息、六维能力、薄弱点和学习记录摘要。

    当前协作包包含可验证的测试学生 ID：demo。
    """

    return get_student_profile_data(student_id)


# 说明（2026-10-13）：role_name / role_id 刻意声明为 Optional[str] = None。
# 客户端侧（官方高代码示例的 _json_schema_to_pydantic）会把「不在 required 里的
# 属性」一律生成为 `Optional[T] = None`，工具 schema 因此对外公布
# `anyOf: [string, null], default: null`，模型完全可能显式发送 null。
# 若服务端仍声明成 `str = ""`，FastMCP/pydantic 会直接以
# `Input should be a valid string [type=string_type]` 拒掉整个工具调用
# （已实测复现）。services 层本就以 `(role_name or "").strip()` 兜底，
# 所以这里放宽为可空是安全的，也让两端的类型契约一致。
@mcp.tool()
def get_role_competency(role_name: Optional[str] = None, role_id: Optional[str] = None):
    """按岗位完整名称或岗位 ID 查询能力要求、技能层级和匹配依据。

    role_name 与 role_id 至少提供一个；同时提供时优先使用 role_id。
    """

    return get_role_competency_data(role_name=role_name, role_id=role_id)


@mcp.tool()
def get_project_status(student_id: str):
    """按学生 ID 查询当前学习路径和项目阶段状态。"""

    return get_project_status_data(student_id)


# 说明（2026-10-16）：以下六个工具补齐「画像 → 检索 → 规划 → 诊断 → 路径更新」闭环。
# 与上面三个工具一样，刻意不写返回类型注解，理由见第 36-40 行。
# 其中 submit_exercise_answer 与 add_learning_branch 带写入语义，会改动容器内
# 01_主工程/backend/data 下的数据；AgentArts 运行时是会话级容器，
# 写入在同一会话内有效，容器回收后释放。
@mcp.tool()
def search_knowledge(student_id: str, query: str, limit: int = 5):
    """在学生的学习资料库中检索与 query 相关的内容，返回带出处的引用片段。

    query 为检索关键词或问题，不超过 200 个字符；limit 为返回条数，1-10，默认 5。
    """

    return search_knowledge_data(student_id, query, limit)


@mcp.tool()
def get_exercise_session(student_id: str, limit: int = 5):
    """按学生 ID 生成一组诊断练习题，返回题面、选项与历史作答状态。

    limit 为题目数量，1-20，默认 5。题目 ID 用于随后调用 submit_exercise_answer。
    """

    return get_exercise_session_data(student_id, limit)


@mcp.tool()
def submit_exercise_answer(student_id: str, question_id: str, answer: str):
    """提交一次练习作答（写入型操作），返回判定结果、解析与路径进度。

    question_id 必须来自 get_exercise_session 的返回；answer 为所选选项文本。
    该操作会写入作答记录，并自动推进对应学习路径阶段的进度。
    """

    return submit_exercise_answer_data(student_id, question_id, answer)


@mcp.tool()
def get_wrong_book(student_id: str):
    """按学生 ID 查询错题本，返回错题分组、能力雷达与薄弱标签汇总。"""

    return get_wrong_book_data(student_id)


@mcp.tool()
def get_learning_evaluation(student_id: str):
    """按学生 ID 查询学习效果评估，返回掌握度、正确率、证据数与改进建议。"""

    return get_learning_evaluation_data(student_id)


@mcp.tool()
def add_learning_branch(
    student_id: str,
    knowledge_node_id: str,
    title: str,
    description: str = "",
    mastery: float = 0,
):
    """向当前学习路径新增一条知识补充分支（写入型操作）。

    knowledge_node_id 取自 get_project_status 返回的路径节点 ID；title 为分支标题；
    description 为学习目标说明；mastery 为 0-100 的初始掌握度。需要该学生已有学习路径。
    """

    return add_learning_branch_data(
        student_id,
        knowledge_node_id,
        title,
        description,
        mastery,
    )


# 说明（2026-10-17，P0-3 加固）：入口从 FastMCP 原生 mcp.run() 换成
# mcp_server.hardening.serve()，在同一个端口上叠加 API Key 鉴权、限流、
# 访问日志脱敏与 /healthz 健康检查。加固层全部默认非阻断（未配
# MCP_API_KEY 就不鉴权、限流阈值很宽），不会影响 AgentArts 运行时里
# 走 IAM 签名的现有链路。应急开关：环境变量 MCP_TRANSPORT_DIRECT=1
# 可退回原生 mcp.run()，见 mcp_server/hardening.py 的模块说明。
if __name__ == "__main__":
    from mcp_server.hardening import serve

    serve(mcp, HOST, PORT)

