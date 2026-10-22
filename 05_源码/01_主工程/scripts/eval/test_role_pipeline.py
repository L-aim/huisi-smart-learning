"""P1-1 第三步的验收脚本：用假实现跑通角色编排，验证步骤间真实传值。

为什么用假实现而不是直连后端服务：
- 这里要验的是「编排逻辑」，即每一步是否用上一步的真实返回值当参数；
- MCP 工具本体需要 fastapi/数据库与 WORKSPACE_DIR，本机没有那套环境，且那 9 个工具
  已分别在云端逐个实测过（见 TEST_RESULTS.md）；
- 假数据刻意模仿真实返回结构（统一 {ok, data} 信封），并复刻真实契约里的失败分支，
  避免「假实现永远成功」把契约问题掩盖掉（云端 trace-3 就是这么暴露出来的）。

另外做一项静态校验：绑定名必须能在 mcp_server/services.py 里找到对应的 *_data 实现，
防止 roles.py 里写的工具名与工具层再次漂移。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "backend" / "app" / "agents"
MCP_SERVICES = PROJECT_ROOT.parent / "mcp_server" / "services.py"

WEAK_POINT = "混淆用例图与需求访谈"
QUESTION_ID = "generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0"
ROLE_NAME = "软件需求分析师"

results: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(f"{'PASS' if ok else 'FAIL'}  {name}{' | ' + detail if detail else ''}")


def load_agents_package():
    """按文件路径加载 agents 子包，绕开 app/__init__.py 里的 Web 依赖。"""
    if "rp_pkg" in sys.modules:
        return sys.modules["rp_pkg"]

    pkg = types.ModuleType("rp_pkg")
    pkg.__path__ = [str(AGENTS_DIR)]
    sys.modules["rp_pkg"] = pkg

    def load(name: str):
        spec = importlib.util.spec_from_file_location(f"rp_pkg.{name}", AGENTS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"rp_pkg.{name}"] = module
        spec.loader.exec_module(module)
        return module

    load("roles")
    load("role_pipeline")
    return pkg


def make_registry(calls: list[tuple[str, dict]], *, fail_submit: bool = False):
    def record(name: str, payload):
        calls.append((name, payload))
        return payload

    def get_role_competency(**kwargs):
        # 复刻真实契约：没有 role_name / role_id 一律失败（mcp_server/services.py:141）
        if not kwargs.get("role_name") and not kwargs.get("role_id"):
            return record(
                "get_role_competency",
                {"ok": False, "code": "MISSING_ROLE_QUERY", "message": "role_name 和 role_id 至少提供一个。"},
            )
        return record("get_role_competency", {"ok": True, "data": {"role_name": kwargs.get("role_name")}})

    def submit(**kwargs):
        if fail_submit:
            return record(
                "submit_exercise_answer",
                {"ok": False, "code": "INVALID_QUESTION", "message": "题目不存在。"},
            )
        return record("submit_exercise_answer", {"ok": True, "data": {"path_progress": {"correct": True, "mastery": 33}}})

    return {
        "get_role_competency": get_role_competency,
        "get_student_profile": lambda **kw: record(
            "get_student_profile",
            # 真实返回的字段是 data.weaknesses（顶层），不是 data.profile.weak_points
            {"ok": True, "data": {"student_id": "demo", "weaknesses": [WEAK_POINT, "资源推送"], "abilities": [], "learning_summary": {}}},
        ),
        "search_knowledge": lambda **kw: record("search_knowledge", {"ok": True, "data": {"results": [{"c": 1}, {"c": 2}]}}),
        "get_project_status": lambda **kw: record(
            "get_project_status",
            {"ok": True, "data": {"student_id": "demo", "path": {"current_stage": {"id": "stage-1", "status": "current"}, "nodes": [{"id": "stage-1", "status": "current"}]}}},
        ),
        "get_exercise_session": lambda **kw: record(
            "get_exercise_session", {"ok": True, "data": {"questions": [{"id": QUESTION_ID}]}}
        ),
        "submit_exercise_answer": submit,
        "get_wrong_book": lambda **kw: record("get_wrong_book", {"ok": True, "data": {"corrections": [{"q": 1}, {"q": 2}]}}),
        "add_learning_branch": lambda **kw: record(
            "add_learning_branch", {"ok": True, "data": {"created": True, "branch_id": "branch-abc"}}
        ),
        "get_learning_evaluation": lambda **kw: record(
            "get_learning_evaluation", {"ok": True, "data": {"evaluation": {"mastery": 0, "accuracy": 33.3}}}
        ),
    }


CHAIN_WITHOUT_ROLE = [
    "get_student_profile",
    "search_knowledge",
    "get_project_status",
    "get_exercise_session",
    "submit_exercise_answer",
    "add_learning_branch",
    "get_wrong_book",
    "get_learning_evaluation",
]
CHAIN_WITH_ROLE = ["get_role_competency"] + CHAIN_WITHOUT_ROLE


def check_tool_layer_alignment(pipeline) -> None:
    if not MCP_SERVICES.exists():
        check("工具层源码可读", False, str(MCP_SERVICES))
        return
    source = MCP_SERVICES.read_text(encoding="utf-8")
    missing = [tool for tool in sorted(pipeline.bound_tools()) if not re.search(rf"^def {tool}_data\(", source, re.M)]
    check("绑定名与工具层实现对齐", not missing, f"缺失={missing}" if missing else f"{len(pipeline.bound_tools())} 个全部命中")


def main() -> int:
    load_agents_package()
    roles = sys.modules["rp_pkg.roles"]
    pipeline = sys.modules["rp_pkg.role_pipeline"]

    check(
        "roles 五个角色齐全",
        [role["key"] for role in roles.ROLES] == ["profile", "knowledge", "path", "diagnose", "update"],
    )
    check_tool_layer_alignment(pipeline)

    registry_stub = make_registry([])
    check("9 个绑定工具全部有实现", list(pipeline.missing_bindings(registry_stub)) == [], str(pipeline.missing_bindings(registry_stub)))

    # ---- 有岗位标识：九步全跑 ----
    calls: list[tuple[str, dict]] = []
    outcome = pipeline.RolePipeline(make_registry(calls)).run("demo", answer="B", role_name=ROLE_NAME)
    steps = outcome["trace"]
    tools = [step["tool"] for step in steps]
    by_tool = {step["tool"]: step for step in steps}

    check("有岗位时 9 步按角色顺序执行", tools == CHAIN_WITH_ROLE, str(tools))
    check("主控带上了岗位名", by_tool["get_role_competency"]["handoff"] == {"role_name": ROLE_NAME}, str(by_tool["get_role_competency"]["handoff"]))
    check("检索关键词来自画像薄弱点", by_tool["search_knowledge"]["handoff"].get("query") == WEAK_POINT)
    check("提交的问题 id 来自出题结果", by_tool["submit_exercise_answer"]["handoff"].get("question_id") == QUESTION_ID)
    check(
        "知识分支节点来自路径状态",
        by_tool["add_learning_branch"]["handoff"].get("knowledge_node_id") == "stage-1"
        and by_tool["add_learning_branch"]["handoff"].get("title") == WEAK_POINT,
    )
    check("每步都真的调了工具", [name for name, _ in calls] == CHAIN_WITH_ROLE, str([name for name, _ in calls]))
    check("返回聚合正确", outcome["correct"] is True and outcome["branch_id"] == "branch-abc" and outcome["knowledge_hits"] == 2)

    # ---- 没有岗位标识：跳过主控，不拿空参去撞失败 ----
    calls_no_role: list[tuple[str, dict]] = []
    outcome_no_role = pipeline.RolePipeline(make_registry(calls_no_role)).run("demo")
    check(
        "无岗位时跳过主控且为 8 步",
        [step["tool"] for step in outcome_no_role["trace"]] == CHAIN_WITHOUT_ROLE and outcome_no_role["role_matched"] is False,
    )

    # ---- 空参主控必然失败：证明我们没有假装它成功 ----
    try:
        pipeline.RolePipeline(make_registry([])).run("demo", role_name="")
        check("空参主控会被跳过而不是失败", True)
    except pipeline.ToolCallFailed as exc:
        check("空参主控会被跳过而不是失败", False, str(exc))

    try:
        pipeline.RolePipeline(make_registry([])).run("demo", role_id="")
        check("空岗位编号同样跳过", True)
    except pipeline.ToolCallFailed as exc:
        check("空岗位编号同样跳过", False, str(exc))

    # ---- 中途 ok=false：必须就地停，不许继续跑 ----
    failing_calls: list[tuple[str, dict]] = []
    try:
        pipeline.RolePipeline(make_registry(failing_calls, fail_submit=True)).run("demo", role_name=ROLE_NAME)
        check("工具失败时编排中止", False, "未抛异常")
    except pipeline.ToolCallFailed as exc:
        check("工具失败时编排中止", exc.code == "INVALID_QUESTION", str(exc))
    check(
        "中止后没有继续调用后续工具",
        [name for name, _ in failing_calls] == ["get_role_competency", "get_student_profile", "search_knowledge", "get_project_status", "get_exercise_session", "submit_exercise_answer"],
        str([name for name, _ in failing_calls]),
    )

    # ---- 缺绑定与缺数据都必须报错 ----
    broken = dict(make_registry([]))
    broken.pop("get_exercise_session")
    try:
        pipeline.RolePipeline(broken).run("demo")
        check("缺工具时报错", False, "未抛异常")
    except pipeline.MissingToolBinding as exc:
        check("缺工具时报错", "get_exercise_session" in str(exc), str(exc))

    no_weak = dict(make_registry([]))
    no_weak["get_student_profile"] = lambda **kw: {"ok": True, "data": {"student_id": "demo", "weaknesses": []}}
    try:
        pipeline.RolePipeline(no_weak).run("demo")
        check("无薄弱点时报错", False, "未抛异常")
    except pipeline.MissingToolBinding as exc:
        check("无薄弱点时报错", "weaknesses" in str(exc), str(exc))

    print("\n".join(results))
    failures = [line for line in results if line.startswith("FAIL")]
    print(f"RESULT: {len(results) - len(failures)}/{len(results)} 通过")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
