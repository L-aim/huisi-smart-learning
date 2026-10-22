from __future__ import annotations

import sys

from testlib import assert_success, assert_true, load_fixture, record_result, request_json, run_case


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
INPUTS = load_fixture("sample_inputs.json")
LOCAL_STUDENT_ID = "demo"


def post(path: str, payload: dict):
    return request_json(BASE_URL, "POST", path, payload)


def get(path: str):
    return request_json(BASE_URL, "GET", path)


def flow_a_local_evidence_loop():
    profile = assert_success(get(f"/api/profile/{LOCAL_STUDENT_ID}/overview"), "profile overview")
    assert_true(profile.get("dimensions"), "profile abilities missing")
    resources = assert_success(get(f"/api/workshop/resources?student_id={LOCAL_STUDENT_ID}"), "resource list")
    assert_true(resources.get("resources"), "local resources empty")
    exercise = assert_success(get(f"/api/exercise/stats?student_id={LOCAL_STUDENT_ID}"), "exercise stats")
    assert_true((exercise.get("stats") or {}).get("total", 0) > 0, "local exercise evidence empty")
    evaluation = assert_success(get(f"/api/evaluate/overview?student_id={LOCAL_STUDENT_ID}"), "evaluation overview")
    assert_true("score" in evaluation and "evidence" in evaluation, "evaluation evidence missing")
    dashboard = assert_success(get(f"/api/dashboard/overview?student_id={LOCAL_STUDENT_ID}"), "dashboard overview")
    assert_true(dashboard.get("journey") and dashboard.get("next_actions"), "learning loop summary incomplete")


def flow_b_knowledge_boundary():
    inside = assert_success(post("/api/knowledge/ask", {"student_id": LOCAL_STUDENT_ID, "question": "单链表插入操作是什么？"}), "knowledge inside")
    assert_true(inside.get("answer"), "inside knowledge answer missing")
    outside = assert_success(post("/api/knowledge/ask", {"student_id": LOCAL_STUDENT_ID, "question": INPUTS["out_of_scope_question"]}), "knowledge outside")
    answer = outside.get("answer") or {}
    assert_true("不足" in answer.get("markdown", ""), "outside knowledge should state limitation")


def flow_c_no_key_is_explicit_and_safe():
    health = assert_success(get("/api/health"), "demo health")
    provider = health.get("ai_provider") or {}
    if provider.get("configured"):
        assert_true(provider.get("demo_mode") is False, "configured provider cannot be demo mode")
        return
    assert_true(provider.get("demo_mode") is True, "no-key mode flag missing")
    resp = post("/api/agents/generate-resources", {"student_id": LOCAL_STUDENT_ID, "topic": "链表"})
    body = resp.get("body") or {}
    assert_true(resp.get("status", 500) < 500, "no-key resource call returned server error")
    assert_true(body.get("success") is False, "no-key resource call must not claim generated content")
    assert_true(bool((body.get("error") or {}).get("message")), "no-key error must be explainable")


def main() -> int:
    results: list[dict] = []
    for case in (flow_a_local_evidence_loop, flow_b_knowledge_boundary, flow_c_no_key_is_explicit_and_safe):
        run_case(results, case.__name__, case)
    record_result("integration_flow.json", results)
    return 1 if any(item["status"] != "passed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

