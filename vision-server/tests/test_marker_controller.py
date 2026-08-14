import importlib.util
import sys
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
    assert right.left_pwm < 0 < right.right_pwm
    assert left.right_pwm < 0 < left.left_pwm


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
