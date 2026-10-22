"""P1-1 绑定校验：orchestrator 的生成智能体是否都挂了真实 MCP 工具。

只用标准库、不 import 后端应用，避免触发 fastapi 依赖。
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]          # 01_主工程
ORCH = ROOT / "backend" / "app" / "agents" / "orchestrator.py"
SERVER = ROOT.parents[0] / "mcp_server" / "server.py"       # ICT/mcp_server/server.py


def main() -> int:
    text = ORCH.read_text(encoding="utf-8")
    ast.parse(text)
    real = set(
        re.findall(
            r"@mcp\.tool\([^)]*\)\s*\ndef\s+([A-Za-z_][A-Za-z0-9_]*)",
            SERVER.read_text(encoding="utf-8"),
        )
    )
    bound: list[str] = []
    for block in re.findall(r"tools=\(([^)]*)\)", text):
        bound.extend(re.findall(r'"([a-z_]+)"', block))
    unknown = sorted(set(bound) - real)
    empty_specs = len(re.findall(r"AgentSpec\(", text)) - len(re.findall(r"tools=\(", text))
    print("AST-OK")
    print(f"mcp_tools={len(real)} bound_refs={len(bound)} distinct={len(set(bound))}")
    print(f"unknown_tools={unknown or 'none'}")
    print(f"specs_without_tools={empty_specs}")
    ok = not unknown and empty_specs == 0
    print("BINDING-CHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
