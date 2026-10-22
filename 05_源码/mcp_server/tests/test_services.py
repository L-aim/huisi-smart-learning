from __future__ import annotations

import unittest

from mcp_server.services import get_project_status_data, get_role_competency_data, get_student_profile_data


class StudentProfileToolTests(unittest.TestCase):
    def test_demo_profile_uses_project_data(self) -> None:
        result = get_student_profile_data("demo")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["student_id"], "demo")
        self.assertGreater(len(result["data"]["abilities"]), 0)
        self.assertEqual(result["meta"]["data_mode"], "bundled_demo_data")

    def test_unknown_student_has_explainable_error(self) -> None:
        result = get_student_profile_data("not-present")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "STUDENT_NOT_FOUND")

    def test_path_traversal_is_rejected(self) -> None:
        result = get_student_profile_data("../demo")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_STUDENT_ID")


class RoleCompetencyToolTests(unittest.TestCase):
    def test_role_by_id(self) -> None:
        result = get_role_competency_data(role_id="job_001")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["role_name"], "Java开发工程师")
        self.assertIn("Java", result["data"]["requirements"]["hard_skills"])
        self.assertEqual(result["data"]["matching_basis"]["match_type"], "exact_role_id")

    def test_role_by_name(self) -> None:
        result = get_role_competency_data(role_name="前端开发工程师")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["role_id"], "job_002")

    def test_missing_role_query(self) -> None:
        result = get_role_competency_data()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "MISSING_ROLE_QUERY")


class ProjectStatusToolTests(unittest.TestCase):
    def test_demo_status(self) -> None:
        result = get_project_status_data("demo")
        self.assertTrue(result["ok"], result)
        self.assertIn("path", result["data"])


if __name__ == "__main__":
    unittest.main()

