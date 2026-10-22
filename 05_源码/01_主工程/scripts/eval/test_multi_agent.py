"""多 Agent 多进程运行时的本地验收（不联网、不依赖后端 Web 栈）。

验收七组：
1. 有岗位：九步全 ok，且步骤顺序固定
2. 角色 = 进程：7 个角色拿到 7 个互不相同、且都与主控不同的 pid
3. 每步 pid 与其角色绑定一致（同一角色两次派任务落在同一个 pid）
4. 三处跨步传值命中（weaknesses[0] / questions[0].id / current_stage.id）
5. 无岗位：第 0 步跳过，其余 8 步仍全部执行
6. 工具故障隔离：指定工具抛异常 → 就地中止、后续不再执行，其它角色进程不受影响
7. 缺上文数据：画像没有 weaknesses → MISSING_HANDOFF_DATA 中止
另加静态检查：九个步骤的工具名必须真实存在于注册表。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
AGENTS = os.path.join(PROJECT, "backend", "app", "agents")
for path in (AGENTS, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import multi_agent  # noqa: E402

REGISTRY = "fake_services"
PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS  {name}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"FAIL  {name} | {detail}")


def run_once(**kwargs):
    client = multi_agent.MultiAgentRuntime(REGISTRY, timeout=60)
    return client.run(**kwargs)


def main() -> int:
    print("=== 静态检查 ===")
    missing = multi_agent.MultiAgentRuntime.missing_bindings(REGISTRY)
    check("所有步骤的工具都在注册表里", not missing, f"missing={missing or 'none'}")

    print("\n=== 1/3/4. 有岗位：九步 + 角色即进程 + 跨步传值 ===")
    result = run_once(student_id="demo", answer="B", role_name="前端开发工程师")
    steps = result["steps"]
    check("九步全部执行", len(steps) == 9, f"steps={len(steps)}")
    check("九步全部 ok", result["ok"] and all(s["ok"] for s in steps), f"ok={result['ok']}")
    check(
        "步骤顺序固定",
        [s["tool"] for s in steps]
        == [
            "get_role_competency",
            "get_student_profile",
            "search_knowledge",
            "get_project_status",
            "get_exercise_session",
            "submit_exercise_answer",
            "add_learning_branch",
            "get_wrong_book",
            "get_learning_evaluation",
        ],
        "顺序与 default_steps 一致",
    )

    workers = result["workers"]
    pids = [handle["pid"] for handle in workers.values()]
    check("角色数 = 7", len(workers) == 7, f"roles={sorted(workers)}")
    check("7 个角色 7 个不同进程", len(set(pids)) == 7, f"pids={sorted(set(pids))}")
    check("角色进程都不在主控进程里", os.getpid() not in pids, f"parent={os.getpid()}")

    step_pid_ok = all(s["pid"] == workers[s["role"]]["pid"] for s in steps)
    check("每步 pid 与其角色绑定一致", step_pid_ok, "同角色两次派任务落在同一进程")

    diagnose_pids = {s["pid"] for s in steps if s["role"] == "diagnose"}
    check("diagnose 角色两步入参在同一进程", len(diagnose_pids) == 1, f"pids={diagnose_pids}")

    context = result["context"]
    check(
        "第 3 步检索词取自画像 weaknesses[0]",
        context.get("weak_point") == "混淆用例图与需求访谈",
        f"weak_point={context.get('weak_point')}",
    )
    check(
        "第 6 步题号取自 questions[0].id",
        context.get("question_id") == "generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0",
        f"question_id={context.get('question_id')}",
    )
    knowledge_step = steps[2]
    check(
        "检索工具入参 = 画像薄弱点",
        knowledge_step["arguments"].get("query") == "混淆用例图与需求访谈",
        f"query={knowledge_step['arguments'].get('query')}",
    )
    check(
        "第 7 步节点取自 current_stage.id",
        context.get("stage_id") == "stage-1"
        and steps[6]["arguments"].get("knowledge_node_id") == "stage-1",
        f"knowledge_node_id={steps[6]['arguments'].get('knowledge_node_id')}",
    )
    check("作答判定回传", context.get("correct") is True, f"correct={context.get('correct')}")

    print("\n=== 5. 无岗位：第 0 步跳过 ===")
    result2 = run_once(student_id="demo", answer="B")
    steps2 = result2["steps"]
    check("仍记录 9 条（第 0 条标记 skipped）", len(steps2) == 9, f"steps={len(steps2)}")
    check("第 0 步被跳过", "skipped" in (steps2[0]["handoff"] or ""), f"handoff={steps2[0]['handoff']}")
    check("其余 8 步都执行并通过", result2["ok"] and sum(1 for s in steps2 if s["ok"]) == 8, f"ok={result2['ok']}")

    print("\n=== 6. 工具故障隔离 ===")
    os.environ["FAKE_FAIL_TOOL"] = "search_knowledge"
    try:
        result3 = run_once(student_id="demo", answer="B", role_name="前端开发工程师")
    finally:
        os.environ.pop("FAKE_FAIL_TOOL", None)
    steps3 = result3["steps"]
    check("故障即中止", not result3["ok"], f"ok={result3['ok']}")
    check("停在第 3 步（检索），后续未执行", len(steps3) == 3, f"steps={len(steps3)}")
    check(
        "失败原因如实回传",
        result3["stop_reason"].get("code") == "TOOL_CALL_FAILED"
        and "模拟故障" in str(result3["stop_reason"].get("message")),
        f"stop_reason={result3['stop_reason']}",
    )
    check("其它角色进程仍各自独立", len({h["pid"] for h in result3["workers"].values()}) == 7)

    print("\n=== 7. 缺上文数据 ===")
    os.environ["FAKE_EMPTY_WEAK"] = "1"
    try:
        result4 = run_once(student_id="demo", answer="B", role_name="前端开发工程师")
    finally:
        os.environ.pop("FAKE_EMPTY_WEAK", None)
    check("缺薄弱点即中止", not result4["ok"], f"ok={result4['ok']}")
    check(
        "中止原因是缺上文数据",
        result4["stop_reason"].get("code") == "MISSING_HANDOFF_DATA",
        f"stop_reason={result4['stop_reason']}",
    )
    check("停在第 3 步之前（只跑完前两步）", len(result4["steps"]) == 3, f"steps={len(result4['steps'])}")

    print("\n=== 8. 业务层失败（工具没抛异常，但返回 ok=false）===")
    os.environ["FAKE_BUSINESS_FAIL"] = "search_knowledge"
    try:
        result5 = run_once(student_id="demo", answer="B", role_name="前端开发工程师")
    finally:
        os.environ.pop("FAKE_BUSINESS_FAIL", None)
    check("业务失败也算失败", not result5["ok"], f"ok={result5['ok']}")
    check(
        "失败步骤被标 ok=false（不是继续往下走）",
        len(result5["steps"]) == 3 and result5["steps"][2]["ok"] is False,
        f"steps={len(result5['steps'])}",
    )
    check(
        "stop_reason 透传业务错误码",
        result5["stop_reason"].get("code") == "NO_QUESTION_BANK",
        f"stop_reason={result5['stop_reason']}",
    )

    print(f"\nRESULT: {PASS}/{PASS + FAIL} 通过")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
