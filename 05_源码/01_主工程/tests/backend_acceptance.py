from __future__ import annotations

import sys

from testlib import assert_success, assert_true, load_fixture, record_result, request_json, run_case


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PROFILE = load_fixture("student_profile.json")
INPUTS = load_fixture("sample_inputs.json")
RESOURCE_REQUEST = load_fixture("resource_request.json")
LOCAL_STUDENT_ID = "demo"


def post(path: str, payload: dict):
    return request_json(BASE_URL, "POST", path, payload)


def get(path: str):
    return request_json(BASE_URL, "GET", path)


def health_data() -> dict:
    return assert_success(get("/api/health"), "health")


def ai_configured() -> bool:
    return bool((health_data().get("ai_provider") or {}).get("configured"))


def assert_safe_error(resp: dict, label: str, allowed_codes: set[str]) -> dict:
    status = int(resp.get("status") or 0)
    body = resp.get("body") or {}
    assert_true(status < 500, f"{label}: unsafe HTTP {status}: {body}")
    assert_true(body.get("success") is False, f"{label}: expected success=false: {body}")
    error = body.get("error") or {}
    assert_true(error.get("code") in allowed_codes, f"{label}: unexpected error: {error}")
    assert_true(bool(error.get("message")), f"{label}: missing explainable error message")
    return error


def test_health():
    data = health_data()
    assert_true("backend" in data, "health.data.backend missing")
    assert_true("ai_provider" in data, "health.data.ai_provider missing")
    assert_true("knowledge_base" in data, "health.data.knowledge_base missing")
    assert_true(data.get("data_dir_ready") is True, "health data directory is not ready")


def test_learning_dashboard_unifies_evidence():
    data = assert_success(get(f"/api/dashboard/overview?student_id={LOCAL_STUDENT_ID}"), "dashboard overview")
    assert_true(data.get("learner"), "dashboard learner missing")
    assert_true(data.get("focus"), "dashboard focus missing")
    assert_true(len(data.get("journey") or []) >= 7, "dashboard journey incomplete")
    assert_true(len(data.get("metrics") or []) >= 4, "dashboard metrics incomplete")


def test_profile_chat_extracts_six_dimensions():
    payload = {
        "student_id": PROFILE["student_id"],
        "messages": [{"role": "user", "content": INPUTS["profile_input"]}],
        "major": PROFILE["major"],
        "goals": PROFILE["learning_goal"],
    }
    data = assert_success(post("/api/profile/chat", payload), "profile chat")
    snapshot = data.get("snapshot") or {}
    assert_true(len(snapshot.get("dimensions") or {}) >= 6, "profile dimensions < 6")


def test_profile_empty_input_is_explainable():
    resp = post("/api/profile/extract", {"student_id": PROFILE["student_id"], "question": ""})
    assert_safe_error(resp, "profile empty", {"PROFILE_TEXT_REQUIRED"})


def test_resource_generation_or_local_data():
    if ai_configured():
        data = assert_success(post("/api/agents/generate-resources", RESOURCE_REQUEST), "generate resources")
        assert_true(bool(data.get("resources")), "generated resources empty")
        return
    resp = post("/api/agents/generate-resources", RESOURCE_REQUEST)
    assert_safe_error(resp, "generate resources without key", {"RESOURCE_GENERATION_ERROR"})
    local = assert_success(get(f"/api/workshop/resources?student_id={LOCAL_STUDENT_ID}"), "local resources")
    assert_true(bool(local.get("resources")), "bundled demo resources empty")


def test_path_plan_or_local_status():
    if ai_configured():
        data = assert_success(post("/api/path/plan", {"student_id": PROFILE["student_id"], "goals": PROFILE["learning_goal"]}), "path plan")
        assert_true(bool((data.get("path") or {}).get("nodes")), "path nodes empty")
        return
    data = assert_success(get(f"/api/path/overview?student_id={LOCAL_STUDENT_ID}"), "local path overview")
    assert_true("has_plan" in data and "nodes" in data, "local path status contract missing")


def test_recommendations_use_local_resources():
    data = assert_success(post("/api/recommendations", {"student_id": LOCAL_STUDENT_ID}), "recommendations")
    recommendations = data.get("recommendations") or data.get("items") or []
    assert_true(bool(recommendations), "recommendations empty")
    assert_true(all(item.get("reason") for item in recommendations), "recommendation reason missing")


def test_tutor_is_real_or_fails_safely():
    resp = post("/api/tutor/ask", {"student_id": LOCAL_STUDENT_ID, "question": INPUTS["tutor_question"]})
    if ai_configured():
        data = assert_success(resp, "tutor ask")
        assert_true(bool(data.get("markdown")), "tutor markdown missing")
    else:
        assert_safe_error(resp, "tutor without key", {"TUTOR_ERROR"})


def test_evaluation_snapshot_uses_local_evidence():
    data = assert_success(post("/api/evaluation/submit", {"student_id": LOCAL_STUDENT_ID}), "evaluation submit")
    for key in ("score", "mastery", "weak_points", "suggestions"):
        assert_true(key in data, f"evaluation missing {key}")


def test_exercises_generate_and_submit():
    generated = assert_success(post("/api/exercises/generate", {"student_id": LOCAL_STUDENT_ID}), "exercises generate")
    questions = generated.get("questions") or []
    if questions:
        first = questions[0]
        submitted = assert_success(
            post("/api/exercises/submit", {"student_id": LOCAL_STUDENT_ID, "question_id": first["id"], "answer": ""}),
            "exercises submit empty answer",
        )
        assert_true("correct" in submitted and "analysis" in submitted, "exercise diagnosis contract missing")
        return
    stats = assert_success(get(f"/api/exercise/stats?student_id={LOCAL_STUDENT_ID}"), "exercise stats")
    assert_true((stats.get("stats") or {}).get("total", 0) > 0, "bundled diagnosis records empty")
    wrong_book = assert_success(get(f"/api/exercise/wrong-book?student_id={LOCAL_STUDENT_ID}"), "wrong book")
    assert_true(bool(wrong_book.get("records")), "bundled wrong-book records empty")


def test_knowledge_and_multimodal_boundary():
    kb = assert_success(post("/api/knowledge/ask", {"student_id": LOCAL_STUDENT_ID, "question": "单链表插入操作是什么？"}), "knowledge ask")
    assert_true(kb.get("answer"), "knowledge answer missing")
    graph = assert_success(get(f"/api/knowledge/map?student_id={LOCAL_STUDENT_ID}&max_nodes=40"), "knowledge map")
    assert_true("nodes" in graph and "edges" in graph, "knowledge graph nodes/edges missing")
    resp = post("/api/multimodal/generate", {"student_id": LOCAL_STUDENT_ID, "topic": INPUTS["multimodal_request"]})
    if ai_configured():
        assert_success(resp, "multimodal generate")
    else:
        assert_safe_error(resp, "multimodal without key", {"MULTIMODAL_GENERATION_ERROR"})


def test_workshop_export_existing_local_resources():
    data = assert_success(get(f"/api/workshop/resources?student_id={LOCAL_STUDENT_ID}"), "workshop resources")
    assert_true(bool(data.get("resources")), "workshop resources missing")
    export_data = assert_success(post("/api/workshop/export", {"student_id": LOCAL_STUDENT_ID}), "workshop export")
    assert_true(export_data.get("status") in {"ready", "completed"}, "export status invalid")


def main() -> int:
    results: list[dict] = []
    cases = [
        test_health,
        test_learning_dashboard_unifies_evidence,
        test_profile_chat_extracts_six_dimensions,
        test_profile_empty_input_is_explainable,
        test_resource_generation_or_local_data,
        test_path_plan_or_local_status,
        test_recommendations_use_local_resources,
        test_tutor_is_real_or_fails_safely,
        test_evaluation_snapshot_uses_local_evidence,
        test_exercises_generate_and_submit,
        test_knowledge_and_multimodal_boundary,
        test_workshop_export_existing_local_resources,
    ]
    for case in cases:
        run_case(results, case.__name__, case)
    record_result("backend_acceptance.json", results)
    return 1 if any(item["status"] != "passed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

