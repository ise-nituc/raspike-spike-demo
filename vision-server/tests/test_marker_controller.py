import importlib.util
import socket
import sys
import threading
import types
from pathlib import Path

sys.modules.setdefault(
    "cv2", types.SimpleNamespace(flip=lambda frame, axis: frame[::-1])
)
sys.modules.setdefault("numpy", types.SimpleNamespace(ndarray=object))
sys.modules.setdefault("picamera2", types.SimpleNamespace(Picamera2=object))
MODULE_PATH = Path(__file__).parents[1] / "marker_controller.py"
SPEC = importlib.util.spec_from_file_location("marker_controller", MODULE_PATH)
marker_controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = marker_controller
SPEC.loader.exec_module(marker_controller)


def marker(cx, cy, theta):
    blob = marker_controller.ColorBlob(cx, cy, 100.0, [])
    return marker_controller.MarkerState(blob, blob, cx, cy, theta, 30.0)


def test_camera_frame_is_flipped_vertically_only():
    frame = [["top-left", "top-right"], ["bottom-left", "bottom-right"]]

    oriented = marker_controller.orient_camera_frame(frame)

    assert oriented == [frame[1], frame[0]]
    assert oriented[0][0] == "bottom-left"


def test_forward_speed_uses_only_marker_front_back_position():
    ahead = marker_controller.calculate_motor_command(marker(20, 20, 0.0))
    behind = marker_controller.calculate_motor_command(marker(300, 220, 0.0))

    assert ahead.forward > 0
    assert behind.forward < 0
    assert ahead.turn == behind.turn == 0
    assert ahead.left_pwm == ahead.right_pwm
    assert behind.left_pwm == behind.right_pwm


def test_twisting_marker_turns_even_at_image_center():
    right = marker_controller.calculate_motor_command(
        marker(marker_controller.WIDTH / 2, marker_controller.HEIGHT / 2, marker_controller.math.pi / 2)
    )
    left = marker_controller.calculate_motor_command(
        marker(marker_controller.WIDTH / 2, marker_controller.HEIGHT / 2, -marker_controller.math.pi / 2)
    )

    assert right.forward == left.forward == 0
    assert right.right_pwm < 0 < right.left_pwm
    assert left.left_pwm < 0 < left.right_pwm
    assert right.left_pwm == -right.right_pwm
    assert left.left_pwm == -left.right_pwm


def test_output_rises_quickly_after_forward_deadzone():
    just_outside = marker_controller.calculate_motor_command(
        marker(
            marker_controller.WIDTH / 2,
            marker_controller.HEIGHT / 2
            - marker_controller.ACTIVE_RADIUS * 0.30,
            0.0,
        )
    )

    assert just_outside.forward > 0.25
    assert just_outside.left_pwm >= 13
    assert just_outside.right_pwm >= 13


def test_speed_gain_increases_pwm_and_remains_bounded():
    target = marker(marker_controller.WIDTH / 2, 70, 0.0)

    low = marker_controller.calculate_motor_command(target, speed_gain=0.5)
    high = marker_controller.calculate_motor_command(target, speed_gain=2.0)

    assert high.left_pwm > low.left_pwm
    assert high.right_pwm > low.right_pwm
    assert high.left_pwm <= marker_controller.PWM_MAX
    assert high.right_pwm <= marker_controller.PWM_MAX


def test_settings_endpoint_updates_and_clamps_speed_gain(monkeypatch):
    monkeypatch.setattr(
        marker_controller,
        "latest_speed_gain",
        marker_controller.SPEED_GAIN_DEFAULT,
    )
    client = marker_controller.app.test_client()

    response = client.post("/settings", json={"speed_gain": 9})

    assert response.status_code == 200
    assert response.get_json()["speed_gain"] == marker_controller.SPEED_GAIN_MAX
    assert marker_controller.latest_speed_gain == marker_controller.SPEED_GAIN_MAX


def test_settings_endpoint_rejects_invalid_speed_gain():
    client = marker_controller.app.test_client()

    response = client.post("/settings", json={"speed_gain": "fast"})

    assert response.status_code == 400


def test_deadzone_can_be_reduced_for_small_movements():
    target = marker(
        marker_controller.WIDTH / 2,
        marker_controller.HEIGHT / 2
        - marker_controller.ACTIVE_RADIUS * 0.08,
        0.0,
    )

    wide = marker_controller.calculate_motor_command(target, deadzone=0.15)
    narrow = marker_controller.calculate_motor_command(target, deadzone=0.02)

    assert wide.left_pwm == wide.right_pwm == 0
    assert narrow.left_pwm == narrow.right_pwm > 0


def test_settings_endpoint_updates_deadzone(monkeypatch):
    monkeypatch.setattr(
        marker_controller,
        "latest_deadzone",
        marker_controller.DEADZONE_DEFAULT,
    )
    client = marker_controller.app.test_client()

    response = client.post("/settings", json={"deadzone": 0.02})

    assert response.status_code == 200
    assert response.get_json()["deadzone"] == 0.02
    assert marker_controller.latest_deadzone == 0.02


def test_robot_reports_pwm_applied_by_motor_api(monkeypatch):
    monkeypatch.setattr(marker_controller, "latest_command", marker_controller.stop_command())
    server, client = socket.socketpair()
    thread = threading.Thread(
        target=marker_controller.handle_tcp_client,
        args=(server, ("local", 0)),
    )
    thread.start()

    client.sendall(b"GET 1 0 72 68\n")
    assert client.recv(32) == (
        f"0:0:{marker_controller.latest_black_threshold}\n".encode()
    )
    client.close()
    thread.join(timeout=1)

    assert marker_controller.latest_robot_left_pwm == 72
    assert marker_controller.latest_robot_right_pwm == 68


def test_settings_endpoint_updates_black_threshold(monkeypatch):
    monkeypatch.setattr(
        marker_controller,
        "latest_black_threshold",
        marker_controller.BLACK_THRESHOLD_DEFAULT,
    )
    client = marker_controller.app.test_client()

    response = client.post("/settings", json={"black_threshold": 4})

    assert response.status_code == 200
    assert response.get_json()["black_threshold"] == 4
    assert marker_controller.latest_black_threshold == 4


def test_legacy_robot_request_keeps_two_value_response(monkeypatch):
    monkeypatch.setattr(marker_controller, "latest_command", marker_controller.stop_command())
    server, client = socket.socketpair()
    thread = threading.Thread(
        target=marker_controller.handle_tcp_client,
        args=(server, ("legacy", 0)),
    )
    thread.start()

    client.sendall(b"GET 1 0\n")
    assert client.recv(32) == b"0:0\n"
    client.close()
    thread.join(timeout=1)
