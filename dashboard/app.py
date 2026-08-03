"""Raspike demonstration dashboard.

Only units in programs.json can be controlled.  Commands are always passed as an
argument vector (never through a shell).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from flask import Flask, abort, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

BASE_DIR = Path(__file__).resolve().parent
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
UNIT_RE = re.compile(r"^raspike-[a-z0-9-]+\.service$")


@dataclass(frozen=True)
class Program:
    id: str
    category: str
    label: str
    description: str
    unit: str
    web_port: int | None = None


def load_programs(path: Path) -> dict[str, Program]:
    data = json.loads(path.read_text(encoding="utf-8"))
    programs: dict[str, Program] = {}
    for item in data.get("programs", []):
        program = Program(**item)
        if not ID_RE.fullmatch(program.id) or not UNIT_RE.fullmatch(program.unit):
            raise ValueError(f"invalid program registration: {program.id!r}")
        if program.id in programs or program.category not in {"python", "raspike-art"}:
            raise ValueError(f"invalid or duplicate program: {program.id!r}")
        if program.web_port is not None and not 1 <= program.web_port <= 65535:
            raise ValueError(f"invalid web port for program: {program.id!r}")
        programs[program.id] = program
    if not programs:
        raise ValueError("the program manifest is empty")
    return programs


def load_dashboard_settings(path: Path) -> tuple[str, int]:
    settings = json.loads(path.read_text(encoding="utf-8")).get("dashboard", {})
    host = settings.get("host", "0.0.0.0")
    port = settings.get("web_port")
    if not isinstance(host, str) or not host or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid dashboard host or web port")
    return host, port


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=10, check=False)


def create_app(
    manifest: Path | None = None,
    command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = run_command,
) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("RASPIKE_DASHBOARD_SECRET", secrets.token_hex(32))
    manifest_path = manifest or BASE_DIR / "programs.json"
    programs = load_programs(manifest_path)
    dashboard_host, dashboard_port = load_dashboard_settings(manifest_path)
    app.config.update(DASHBOARD_HOST=dashboard_host, DASHBOARD_PORT=dashboard_port)

    def program_or_404(program_id: str) -> Program:
        program = programs.get(program_id)
        if program is None:
            abort(404, description="登録されていないプログラムです")
        return program

    def systemctl(*args: str) -> subprocess.CompletedProcess[str]:
        return command_runner(["sudo", "-n", "systemctl", *args])

    def state(program: Program) -> dict[str, str]:
        result = systemctl("show", program.unit, "--property=ActiveState,SubState", "--value")
        values = result.stdout.strip().splitlines()
        active, sub = (values + ["unknown", "unknown"])[:2]
        if result.returncode:
            active, sub = "unknown", "unknown"
        return {"active_state": active, "sub_state": sub}

    def require_csrf() -> None:
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "-")):
            abort(403, description="CSRFトークンが不正です")

    @app.get("/")
    def index():
        session.setdefault("csrf", secrets.token_urlsafe(24))
        return render_template("index.html", csrf_token=session["csrf"])

    @app.errorhandler(HTTPException)
    def api_error(error: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    @app.get("/api/programs")
    def list_programs():
        browser_host = request.host.rsplit(":", 1)[0]
        result = []
        for program in programs.values():
            item = {**program.__dict__, **state(program)}
            item["web_url"] = (
                f"http://{browser_host}:{program.web_port}/" if program.web_port else None
            )
            result.append(item)
        return jsonify(result)

    @app.post("/api/programs/<program_id>/<action>")
    def change_program(program_id: str, action: str):
        require_csrf()
        program = program_or_404(program_id)
        if action not in {"start", "stop"}:
            abort(404)
        result = systemctl(action, program.unit)
        if result.returncode:
            return jsonify(error=(result.stderr.strip() or "systemctl failed")), 503
        return jsonify(id=program.id, action=action, **state(program))

    @app.get("/api/programs/<program_id>/logs")
    def logs(program_id: str):
        program = program_or_404(program_id)
        try:
            lines = min(300, max(1, int(request.args.get("lines", "100"))))
        except ValueError:
            abort(400, description="linesには整数を指定してください")
        result = command_runner(["journalctl", "--unit", program.unit, "--lines", str(lines), "--no-pager"])
        return jsonify(log=result.stdout, error=result.stderr if result.returncode else "")

    @app.get("/api/system")
    def system_info():
        temperature = None
        try:
            temperature = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
        except (OSError, ValueError):
            pass
        disk = os.statvfs(BASE_DIR)
        return jsonify(
            hostname=socket.gethostname(),
            ip=os.environ.get("RASPIKE_DASHBOARD_IP", request.host.split(":", 1)[0]),
            ssid=os.environ.get("RASPIKE_DASHBOARD_SSID", "raspike-ap"),
            temperature_c=temperature,
            disk_free_bytes=disk.f_bavail * disk.f_frsize,
            uptime_seconds=time.monotonic(),
        )

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=application.config["DASHBOARD_HOST"],
        port=application.config["DASHBOARD_PORT"],
    )
