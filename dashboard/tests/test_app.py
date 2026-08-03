import subprocess
import unittest

from dashboard.app import create_app


class FakeCommands:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:4] == ["sudo", "-n", "systemctl", "show"]:
            return subprocess.CompletedProcess(argv, 0, "inactive\ndead\n", "")
        return subprocess.CompletedProcess(argv, 0, "sample log", "")


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.commands = FakeCommands()
        self.app = create_app(command_runner=self.commands)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.client = self.app.test_client()

    def test_dashboard_port_comes_from_manifest(self):
        self.assertEqual(self.app.config["DASHBOARD_HOST"], "0.0.0.0")
        self.assertEqual(self.app.config["DASHBOARD_PORT"], 5000)

    def token(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["csrf"]

    def test_manifest_is_returned_with_real_state(self):
        response = self.client.get("/api/programs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [p["id"] for p in response.json],
            ["vision-server", "marker-controller", "line-trace-camera", "direct-pwm-camera"],
        )
        self.assertTrue(all(p["active_state"] == "inactive" for p in response.json))
        self.assertEqual(response.json[0]["web_url"], "http://localhost:8080/")
        self.assertIsNone(response.json[2]["web_url"])

    def test_only_registered_program_can_start(self):
        headers = {"X-CSRF-Token": self.token()}
        self.assertEqual(self.client.post("/api/programs/vision-server/start", headers=headers).status_code, 200)
        self.assertIn(["sudo", "-n", "systemctl", "start", "raspike-vision-server.service"], self.commands.calls)
        self.assertEqual(self.client.post("/api/programs/not-allowed/start", headers=headers).status_code, 404)

    def test_state_change_requires_csrf(self):
        self.assertEqual(self.client.post("/api/programs/vision-server/stop").status_code, 403)

    def test_logs_use_fixed_unit_and_bounded_lines(self):
        response = self.client.get("/api/programs/marker-controller/logs?lines=9999")
        self.assertEqual(response.status_code, 200)
        self.assertIn(["journalctl", "--unit", "raspike-marker-controller.service", "--lines", "300", "--no-pager"], self.commands.calls)


if __name__ == "__main__":
    unittest.main()
