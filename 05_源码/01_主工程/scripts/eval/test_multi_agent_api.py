"""走真实 ASGI 请求验证 POST /api/orchestration/multi-agent。

TestClient 不监听端口，但请求是真的经过 FastAPI 路由、依赖注入与线程池，
足以证明「接口这一层」通不通（不是直接调 runtime.run）。
"""
import json
import os
import sys

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ICT = os.path.dirname(PROJECT)
for path in (ICT, PROJECT, os.path.join(PROJECT, "backend")):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("WORKSPACE_DIR", PROJECT)
os.environ.setdefault("DATASOURCE", "csv")


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app

    payload = {
        "student_id": "demo",
        "role_name": "前端开发工程师",
        "answer": "B",
        "timeout_seconds": 180,
    }
    with TestClient(app) as client:
        response = client.post("/api/orchestration/multi-agent", json=payload)
        print("HTTP", response.status_code)
        body = response.json()
        print("SUCCESS", body.get("success"), "ERROR", body.get("error"))
        data = body.get("data") or {}
        print("AVAILABLE", data.get("available"), "OK", data.get("ok"), "RUNTIME", data.get("runtime"))
        workers = data.get("workers") or {}
        print("WORKERS", len(workers), " ".join(f"{k}={v.get('pid')}" for k, v in sorted(workers.items())))
        steps = data.get("steps") or []
        for step in steps:
            print(
                f"  {step.get('index')} {step.get('role'):10s} {step.get('tool'):26s}"
                f" ok={step.get('ok')} pid={step.get('pid')} handoff={str(step.get('handoff') or step.get('error') or '')[:60]}"
            )
        pids = [w.get("pid") for w in workers.values() if isinstance(w.get("pid"), int)]
        print("DISTINCT_WORKER_PIDS", len(set(pids)))
        if data.get("stop_reason"):
            print("STOP_REASON", json.dumps(data["stop_reason"], ensure_ascii=False))
        ok = bool(data.get("ok")) and len(set(pids)) == 7
        print("RESULT", "PASS" if ok else "FAIL")
        return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
