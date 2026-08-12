import subprocess
import tempfile
import unittest
from pathlib import Path

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
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tempdir.name)
        self.app = create_app(command_runner=self.commands, state_dir=self.state_dir)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_dashboard_port_comes_from_manifest(self):
        self.assertEqual(self.app.config["DASHBOARD_HOST"], "0.0.0.0")
        self.assertEqual(self.app.config["DASHBOARD_PORT"], 8082)

    def token(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["csrf"]

    def test_manifest_is_returned_with_real_state(self):
        response = self.client.get("/api/programs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [p["id"] for p in response.json],
            ["vision-server", "marker-controller", "line-trace-camera", "direct-pwm-camera", "ocan2026"],
        )
        self.assertTrue(all(p["active_state"] == "inactive" for p in response.json))
        self.assertEqual(response.json[0]["web_url"], "http://localhost:8080/")
        self.assertIsNone(response.json[2]["web_url"])
        self.assertEqual(response.json[2]["lifecycle_state"], "ready")

    def test_robot_build_state_is_reported_while_service_is_active(self):
        original = self.commands

        def active_commands(argv):
            if argv[:4] == ["sudo", "-n", "systemctl", "show"]:
                return subprocess.CompletedProcess(argv, 0, "active\nrunning\n", "")
            return original(argv)

        app = create_app(command_runner=active_commands, state_dir=self.state_dir)
        app.config.update(TESTING=True, SECRET_KEY="test")
        client = app.test_client()
        (self.state_dir / "robot-line_trace_camera.status").write_text("building\n")
        programs = client.get("/api/programs").json
        line_trace = next(p for p in programs if p["id"] == "line-trace-camera")
        self.assertEqual(line_trace["lifecycle_state"], "building")

    def test_intentional_robot_switch_marks_other_programs_ready(self):
        headers = {"X-CSRF-Token": self.token()}
        response = self.client.post("/api/programs/line-trace-camera/start", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.state_dir / "robot-direct_pwm_camera.status").read_text(), "ready\n")
        self.assertEqual((self.state_dir / "robot-ocan2026.status").read_text(), "ready\n")

    def test_failed_service_is_ready_only_after_intentional_stop(self):
        def failed_commands(argv):
            if argv[:4] == ["sudo", "-n", "systemctl", "show"]:
                return subprocess.CompletedProcess(argv, 0, "failed\nfailed\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        app = create_app(command_runner=failed_commands, state_dir=self.state_dir)
        app.config.update(TESTING=True, SECRET_KEY="test")
        client = app.test_client()
        (self.state_dir / "robot-direct_pwm_camera.status").write_text("running\n")
        direct = next(p for p in client.get("/api/programs").json if p["id"] == "direct-pwm-camera")
        self.assertEqual(direct["lifecycle_state"], "error")

        client.get("/")
        with client.session_transaction() as session:
            token = session["csrf"]
        client.post("/api/programs/direct-pwm-camera/stop", headers={"X-CSRF-Token": token})
        direct = next(p for p in client.get("/api/programs").json if p["id"] == "direct-pwm-camera")
        self.assertEqual(direct["lifecycle_state"], "ready")

    def test_only_registered_program_can_start(self):
        headers = {"X-CSRF-Token": self.token()}
        self.assertEqual(self.client.post("/api/programs/vision-server/start", headers=headers).status_code, 200)
        self.assertIn(["sudo", "-n", "systemctl", "start", "raspike-vision-server.service"], self.commands.calls)
        self.assertEqual(self.client.post("/api/programs/not-allowed/start", headers=headers).status_code, 404)

    def test_state_change_requires_csrf(self):
        self.assertEqual(self.client.post("/api/programs/vision-server/stop").status_code, 403)

    def test_reboot_is_manifest_limited_and_requires_csrf(self):
        self.assertEqual(self.client.post("/api/system/reboot").status_code, 403)
        headers = {"X-CSRF-Token": self.token()}
        self.assertEqual(self.client.post("/api/system/reboot", headers=headers).status_code, 200)
        self.assertIn(["sudo", "-n", "systemctl", "reboot"], self.commands.calls)
        self.assertEqual(self.client.post("/api/system/halt", headers=headers).status_code, 404)

    def test_logs_use_fixed_unit_and_bounded_lines(self):
        response = self.client.get("/api/programs/marker-controller/logs?lines=9999")
        self.assertEqual(response.status_code, 200)
        self.assertIn(["journalctl", "--unit", "raspike-marker-controller.service", "--lines", "300", "--no-pager"], self.commands.calls)


if __name__ == "__main__":
    unittest.main()
