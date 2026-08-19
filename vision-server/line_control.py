import json
import os
import threading


DEFAULT_SETTINGS = {
    "black_value": 40,
    "white_value": 200,
    "vector_gain": 0.8,
    "straight_speed": 45,
    "curve_speed": 25,
    "turn_gain": 55.0,
    "stop_reflection_threshold": 8,
}

SETTING_RANGES = {
    "black_value": (0, 254),
    "white_value": (1, 255),
    "vector_gain": (0.0, 4.0),
    "straight_speed": (0, 100),
    "curve_speed": (0, 100),
    "turn_gain": (0.0, 100.0),
    "stop_reflection_threshold": (0, 100),
}

INTEGER_SETTINGS = {
    "black_value", "white_value", "straight_speed", "curve_speed",
    "stop_reflection_threshold",
}


class LineTraceSettings:
    def __init__(self, path):
        self.path = path
        self._values = DEFAULT_SETTINGS.copy()
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            return self._values.copy()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as source:
                self.update(json.load(source), save=False)
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass
        return self.get()

    def update(self, values, save=True):
        updated = self.get()
        for name, (minimum, maximum) in SETTING_RANGES.items():
            if name not in values:
                continue
            value = max(minimum, min(float(values[name]), maximum))
            updated[name] = int(round(value)) if name in INTEGER_SETTINGS else value

        if updated["black_value"] >= updated["white_value"]:
            raise ValueError("黒基準値は白基準値より小さくしてください")

        with self._lock:
            self._values = updated

        if save:
            temporary_path = self.path + ".tmp"
            with open(temporary_path, "w", encoding="utf-8") as target:
                json.dump(updated, target, ensure_ascii=False, indent=2)
                target.write("\n")
            os.replace(temporary_path, self.path)
        return updated.copy()


def calculate_motor_pwm(steering, confidence, settings):
    if confidence <= 0.0:
        return 0, 0

    curve_ratio = min(1.0, abs(steering))
    base = (
        settings["straight_speed"] * (1.0 - curve_ratio)
        + settings["curve_speed"] * curve_ratio
    )
    turn = settings["turn_gain"] * steering
    left = int(round(max(-100, min(100, base + turn))))
    right = int(round(max(-100, min(100, base - turn))))
    return left, right


def parse_pwm_request(request):
    """PWMクライアント要求を検証し、拡張応答が必要かを返す。"""
    parts = request.split()
    if parts == ["GET"]:
        return False
    if (
        len(parts) == 5
        and parts[0] == "GET"
        and parts[1] in {"0", "1"}
        and parts[2] in {"0", "1"}
    ):
        try:
            int(parts[3])
            int(parts[4])
        except ValueError:
            return None
        return True
