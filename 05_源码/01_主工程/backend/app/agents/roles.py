"""P1-1 第一步：把「多智能体协同」从文案变成可校验的角色定义。

现状问题（《推进计划》P1-1）：后端只有一个流水线类，6 个资源标签没有任何工具绑定，
前端却展示「画像/路径/资源/评估」四个智能体——名不副实。

本模块只做一件事：用数据把 5 个角色的「职责 + 绑定工具 + 输入输出契约」写死下来，
成为唯一事实来源，供编排层与前端读取，并可用源码交叉校验。

设计约束：
- 纯标准库，不 import 后端服务，保证能被独立校验。
- 绑定的工具名必须与 mcp_server/server.py 里真实的 @mcp.tool() 完全一致，
  由 __main__ 里的自检强制验证，防止文档与代码再次漂移。
"""

from __future__ import annotations

import pathlib
import re

ROLES = [
    {
        "key": "profile",
        "name": "画像分析智能体",
        "duty": "读取学习画像与学习摘要，产出学习者基线",
        "tools": ["get_student_profile"],
        "input": "student_id",
        "output": "dimensions、learning_summary",
    },
    {
        "key": "knowledge",
        "name": "知识检索智能体",
        "duty": "在知识库中检索并强制给出处，区分「提到」与「讲解」",
        "tools": ["search_knowledge"],
        "input": "query、student_id",
        "output": "results（含 resource_id / path / score）",
    },
    {
        "key": "path",
        "name": "路径规划智能体",
        "duty": "把基线编排为可执行阶段，并给出当前阶段状态",
        "tools": ["get_project_status"],
        "input": "student_id",
        "output": "path.nodes（stage_id / status / mastery）",
    },
    {
        "key": "diagnose",
        "name": "诊断评估智能体",
        "duty": "出题、判题、汇总错题与学习效果",
        "tools": ["get_exercise_session", "submit_exercise_answer", "get_wrong_book", "get_learning_evaluation"],
        "input": "student_id、answer",
        "output": "questions、correct、wrong_book_summary、mastery/accuracy",
    },
    {
        "key": "update",
        "name": "路径更新智能体",
        "duty": "依据诊断结果给当前阶段加知识补充分支",
        "tools": ["add_learning_branch"],
        "input": "student_id、topic",
        "output": "branch_id、parent_stage_id",
    },
]

# 未被任何角色绑定的工具必须显式说明归属，避免出现「无主工具」
UNASSIGNED_NOTE = {
    "get_role_competency": "岗位能力口径，由主控在规划前调用，不单独设角色",
}

SERVER_PY = pathlib.Path(__file__).resolve().parents[4] / "mcp_server" / "server.py"


def real_tools(server: pathlib.Path) -> set[str]:
    text = server.read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\([^)]*\)\s*\ndef\s+([A-Za-z_][A-Za-z0-9_]*)", text))


def main() -> int:
    bound = [tool for role in ROLES for tool in role["tools"]]
    duplicates = sorted({t for t in bound if bound.count(t) > 1})
    tools = real_tools(SERVER_PY)
    unknown = sorted(set(bound) - tools)
    uncovered = sorted(tools - set(bound) - set(UNASSIGNED_NOTE))

    print(f"roles={len(ROLES)} bound_tools={len(set(bound))}/{len(tools)}")
    print(f"duplicated_bindings={duplicates or 'none'}")
    print(f"unknown_tools={unknown or 'none'}")
    print(f"uncovered_tools={uncovered or 'none'}")
    ok = not duplicates and not unknown and not uncovered
    print("SELF-CHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
