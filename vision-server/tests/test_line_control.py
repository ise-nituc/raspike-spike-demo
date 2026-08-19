import os
import sys
import tempfile
import unittest

try:
    import cv2
    import numpy as np
except ModuleNotFoundError:
    cv2 = None

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from line_control import LineTraceSettings, calculate_motor_pwm, parse_pwm_request
if cv2 is not None:
    from detect_line import estimate_steering


@unittest.skipIf(cv2 is None, "OpenCV is not installed")
class LineDetectionTest(unittest.TestCase):
    def test_vector_gain_strengthens_right_curve(self):
        image = np.full((480, 640, 3), 220, dtype=np.uint8)
        cv2.line(image, (400, 260), (320, 420), (20, 20, 20), 30)

        without_vector, confidence, _ = estimate_steering(
            image, black_value=20, white_value=220, vector_gain=0
        )
        with_vector, _, debug = estimate_steering(
            image, black_value=20, white_value=220, vector_gain=1.5
        )

        self.assertGreater(confidence, 0)
        self.assertGreater(debug["vector_steering"], 0)
        self.assertGreater(with_vector, without_vector)


class MotorControlTest(unittest.TestCase):
    def test_curve_reduces_base_speed_and_turns_right(self):
        settings = {
            "straight_speed": 50,
            "curve_speed": 20,
            "turn_gain": 40,
        }
        left, right = calculate_motor_pwm(1.0, 1.0, settings)
        self.assertEqual((left, right), (60, -20))

    def test_line_loss_stops(self):
        settings = {
            "straight_speed": 50,
            "curve_speed": 20,
            "turn_gain": 40,
        }
        self.assertEqual(calculate_motor_pwm(0.5, 0.0, settings), (0, 0))

    def test_settings_validate_and_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            store = LineTraceSettings(path)
            store.update({"black_value": 30, "white_value": 150})
            reloaded = LineTraceSettings(path)
            self.assertEqual(reloaded.load()["black_value"], 30)
            with self.assertRaises(ValueError):
                store.update({"black_value": 200, "white_value": 100})

    def test_current_pwm_request_uses_extended_response(self):
        self.assertTrue(parse_pwm_request("GET 1 0 42 38"))

    def test_current_pwm_request_accepts_sensor_rgb(self):
        self.assertTrue(parse_pwm_request("GET 1 0 42 38 120 640 180"))

    def test_legacy_pwm_request_uses_legacy_response(self):
        self.assertFalse(parse_pwm_request("GET"))

    def test_invalid_pwm_request_is_rejected(self):
        self.assertIsNone(parse_pwm_request("GET 1 0 unknown 38"))
        self.assertIsNone(parse_pwm_request("GET 1 0"))


if __name__ == "__main__":
    unittest.main()
