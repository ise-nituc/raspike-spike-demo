#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
赤＋緑の2色マーカーをカメラで検出し、
ぬいぐるみ操作用の left_pwm / right_pwm を計算するサンプル。

想定:
- Raspberry Pi + Camera Module
- Picamera2
- OpenCV
- 赤と緑のシールをぬいぐるみ底面に貼る
- 赤 -> 緑 の方向を「ぬいぐるみの前方向」とする

操作:
- マーカー中心が画像中心付近: 停止
- 画像中心から離れるほど: 操作強度が増える
- 赤→緑の向き:
    上    : 前進
    右    : 右旋回
    下    : 後退
    左    : 左旋回
"""

import time
import math
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string
from picamera2 import Picamera2


# ============================================================
# 基本設定
# ============================================================

WIDTH = 320
HEIGHT = 240

# モータ出力設定
PWM_MAX = 50

# 操作領域設定
# 画像中心からこの距離まで離すと最大操作量になる
ACTIVE_RADIUS = min(WIDTH, HEIGHT) * 0.40

# 中心付近の停止領域
DEADZONE = 0.15

# 操作量カーブ
# 1.0: 線形
# 1.5〜2.0: 中心付近を鈍く、外側で強く
GAMMA = 1.5

# 旋回の効き
TURN_GAIN = 1.0

# 検出面積の最小値
MIN_RED_AREA = 80
MIN_GREEN_AREA = 80

# 赤と緑の重心が近すぎる場合は向きが不安定なので無効にする
MIN_MARKER_DISTANCE = 20.0

# 見失ったときに停止するまでの猶予秒数
LOST_TIMEOUT_SEC = 0.3

# Webサーバ設定
WEB_HOST = "0.0.0.0"
WEB_PORT = 8081
WEB_INTERVAL_SEC = 0.1
JPEG_QUALITY = 70


latest_frame = None
latest_command = None
latest_marker_found = False
latest_processing_ms = 0.0
state_lock = threading.Lock()

app = Flask(__name__)


# ============================================================
# データ構造
# ============================================================

@dataclass
class ColorBlob:
    cx: float
    cy: float
    area: float
    contour: np.ndarray


@dataclass
class MarkerState:
    red: ColorBlob
    green: ColorBlob
    cx: float
    cy: float
    theta: float
    marker_distance: float


@dataclass
class MotorCommand:
    left_pwm: int
    right_pwm: int
    strength: float
    forward: float
    turn: float
    distance_ratio: float
    theta_deg: float


# ============================================================
# ユーティリティ
# ============================================================

def clip(value, low, high):
    return max(low, min(value, high))


def normalize_motor_pair(left, right):
    """
    左右の比率を保ったまま -1.0〜+1.0 に収める。
    """
    peak = max(1.0, abs(left), abs(right))
    return left / peak, right / peak


def angle_deg(rad):
    return math.degrees(rad)


# ============================================================
# マスク生成
# ============================================================

def make_red_mask(frame_bgr):
    """
    HSVで赤領域を抽出する。
    赤はHueの0付近と179付近に分かれるため、2範囲を合成する。
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    # 初期値。照明に応じて調整する。
    lower_red1 = np.array([0, 80, 60])
    upper_red1 = np.array([12, 255, 255])

    lower_red2 = np.array([170, 80, 60])
    upper_red2 = np.array([179, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    return mask


def make_green_mask(frame_bgr):
    """
    HSVで緑領域を抽出する。
    蛍光緑・緑テープ等を想定。
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    # 初期値。実物の緑色に応じて調整する。
    lower_green = np.array([40, 60, 50])
    upper_green = np.array([90, 255, 255])

    mask = cv2.inRange(hsv, lower_green, upper_green)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    return mask


# ============================================================
# 色領域検出
# ============================================================

def find_largest_blob(mask, min_area):
    """
    マスク画像から最大の輪郭を取り、その重心を返す。
    """
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)

    if area < min_area:
        return None

    m = cv2.moments(contour)
    if m["m00"] == 0:
        return None

    cx = m["m10"] / m["m00"]
    cy = m["m01"] / m["m00"]

    return ColorBlob(cx=cx, cy=cy, area=area, contour=contour)


def detect_marker(frame_bgr):
    """
    赤・緑マーカーを検出する。

    戻り値:
        marker_state, red_mask, green_mask

    marker_state が None の場合は検出失敗。
    """
    red_mask = make_red_mask(frame_bgr)
    green_mask = make_green_mask(frame_bgr)

    red = find_largest_blob(red_mask, MIN_RED_AREA)
    green = find_largest_blob(green_mask, MIN_GREEN_AREA)

    if red is None or green is None:
        return None, red_mask, green_mask

    # 赤・緑の中点をマーカー中心とする
    marker_cx = (red.cx + green.cx) / 2.0
    marker_cy = (red.cy + green.cy) / 2.0

    # 赤 -> 緑 のベクトル
    vx = green.cx - red.cx

    # 画像座標では下方向が +y なので、上を正にする
    vy = red.cy - green.cy

    marker_distance = math.sqrt(vx * vx + vy * vy)

    if marker_distance < MIN_MARKER_DISTANCE:
        return None, red_mask, green_mask

    # theta:
    # 緑が上    -> 0度
    # 緑が右    -> +90度
    # 緑が下    -> 180度
    # 緑が左    -> -90度
    theta = math.atan2(vx, vy)

    marker = MarkerState(
        red=red,
        green=green,
        cx=marker_cx,
        cy=marker_cy,
        theta=theta,
        marker_distance=marker_distance,
    )

    return marker, red_mask, green_mask


# ============================================================
# モータ指令計算
# ============================================================

def calculate_motor_command(marker):
    """
    マーカー状態から left_pwm / right_pwm を計算する。
    """

    image_cx = WIDTH / 2.0
    image_cy = HEIGHT / 2.0

    # 画像中心からマーカー中心までのずれ
    dx = marker.cx - image_cx
    dy = image_cy - marker.cy  # 上を正にする

    distance = math.sqrt(dx * dx + dy * dy)

    # 0.0〜1.0に正規化
    r = clip(distance / ACTIVE_RADIUS, 0.0, 1.0)

    # デッドゾーン処理
    if r <= DEADZONE:
        strength = 0.0
    else:
        strength = (r - DEADZONE) / (1.0 - DEADZONE)
        strength = strength ** GAMMA

    # 向きから前後成分・旋回成分を計算
    forward = strength * math.cos(marker.theta)
    turn = strength * math.sin(marker.theta)

    # 差動二輪への変換
    left = forward - TURN_GAIN * turn
    right = forward + TURN_GAIN * turn

    # 比率を保って -1.0〜+1.0 に収める
    left, right = normalize_motor_pair(left, right)

    left_pwm = int(round(PWM_MAX * left))
    right_pwm = int(round(PWM_MAX * right))

    return MotorCommand(
        left_pwm=left_pwm,
        right_pwm=right_pwm,
        strength=strength,
        forward=forward,
        turn=turn,
        distance_ratio=r,
        theta_deg=angle_deg(marker.theta),
    )


def stop_command():
    return MotorCommand(
        left_pwm=0,
        right_pwm=0,
        strength=0.0,
        forward=0.0,
        turn=0.0,
        distance_ratio=0.0,
        theta_deg=0.0,
    )


# ============================================================
# ロボットへの送信部分
# ============================================================

def send_motor_command(cmd):
    """
    ここを実機用に置き換える。

    例:
    - TCP/UDPでC++制御プログラムへ送る
    - 共有ファイルへ書く
    - WebSocketで送る
    - SPIKE側へ送る

    今はデバッグ表示のみ。
    """
    print(
        f"\rL={cmd.left_pwm:+4d}  R={cmd.right_pwm:+4d}  "
        f"str={cmd.strength:.2f}  "
        f"theta={cmd.theta_deg:+6.1f}",
        end="",
        flush=True
    )


# ============================================================
# 描画
# ============================================================

def draw_debug_view(frame_bgr, marker, cmd, processing_ms):
    view = frame_bgr.copy()

    image_cx = int(WIDTH / 2)
    image_cy = int(HEIGHT / 2)

    # 画像中心と有効半径
    cv2.circle(view, (image_cx, image_cy), 4, (255, 0, 0), -1)
    cv2.circle(view, (image_cx, image_cy), int(ACTIVE_RADIUS), (255, 0, 0), 1)

    # デッドゾーン
    cv2.circle(
        view,
        (image_cx, image_cy),
        int(ACTIVE_RADIUS * DEADZONE),
        (100, 100, 255),
        1
    )

    if marker is None:
        cv2.putText(
            view,
            "MARKER NOT FOUND",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )
    else:
        # 赤・緑輪郭
        cv2.drawContours(view, [marker.red.contour], -1, (0, 0, 255), 2)
        cv2.drawContours(view, [marker.green.contour], -1, (0, 255, 0), 2)

        # 赤・緑重心
        red_pt = (int(marker.red.cx), int(marker.red.cy))
        green_pt = (int(marker.green.cx), int(marker.green.cy))
        center_pt = (int(marker.cx), int(marker.cy))

        cv2.circle(view, red_pt, 5, (0, 0, 255), -1)
        cv2.circle(view, green_pt, 5, (0, 255, 0), -1)
        cv2.circle(view, center_pt, 5, (255, 255, 0), -1)

        # 赤→緑の方向
        cv2.arrowedLine(
            view,
            red_pt,
            green_pt,
            (0, 255, 255),
            3,
            tipLength=0.25
        )

        # 画像中心からマーカー中心への線
        cv2.line(
            view,
            (image_cx, image_cy),
            center_pt,
            (255, 255, 0),
            1
        )

        text1 = (
            f"L={cmd.left_pwm:+d} R={cmd.right_pwm:+d} "
            f"str={cmd.strength:.2f} dist={cmd.distance_ratio:.2f}"
        )
        text2 = (
            f"theta={cmd.theta_deg:+.1f} "
            f"forward={cmd.forward:+.2f} turn={cmd.turn:+.2f}"
        )

        cv2.putText(
            view,
            text1,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2
        )

        cv2.putText(
            view,
            text2,
            (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2
        )

    cv2.putText(
        view,
        f"{processing_ms:.1f} ms",
        (10, HEIGHT - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1
    )

    return view


# ============================================================
# メイン
# ============================================================

def vision_loop():
    global latest_frame
    global latest_command
    global latest_marker_found
    global latest_processing_ms

    picam2 = Picamera2()

    config = picam2.create_preview_configuration(
        main={
            "size": (WIDTH, HEIGHT),
            "format": "RGB888",
        }
    )

    picam2.configure(config)
    picam2.start()

    # 露出やホワイトバランスが落ち着くのを待つ
    time.sleep(1.0)

    last_seen_time = 0.0
    last_cmd = stop_command()

    print("marker detection started")

    try:
        while True:
            loop_t0 = time.perf_counter()

            frame_rgb = picam2.capture_array()
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            marker, red_mask, green_mask = detect_marker(frame_bgr)

            now = time.perf_counter()

            if marker is not None:
                cmd = calculate_motor_command(marker)
                last_seen_time = now
                last_cmd = cmd
            else:
                # 一瞬見失っただけなら直前値を少しだけ保持してもよい。
                # 安全寄りにするなら即停止でもよい。
                if now - last_seen_time <= LOST_TIMEOUT_SEC:
                    cmd = last_cmd
                else:
                    cmd = stop_command()

            send_motor_command(cmd)

            processing_ms = (time.perf_counter() - loop_t0) * 1000.0
            view = draw_debug_view(frame_bgr, marker, cmd, processing_ms)

            with state_lock:
                latest_frame = view
                latest_command = cmd
                latest_marker_found = marker is not None
                latest_processing_ms = processing_ms

    finally:
        # 終了時は停止指令を出す
        send_motor_command(stop_command())
        picam2.stop()
        print("\n終了しました。")


@app.route("/")
def index():
    return render_template_string("""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marker Controller</title>
  <style>
    body { font-family: sans-serif; margin: 0; background: #111; color: #eee; text-align: center; }
    main { max-width: 960px; margin: auto; padding: 1rem; }
    img { width: 100%; border: 2px solid #555; border-radius: 8px; }
    code { color: #8f8; }
  </style>
</head>
<body>
  <main>
    <h1>Marker Controller</h1>
    <p>赤・緑マーカーの検出結果とモーター指令を表示しています。</p>
    <img src="/video" alt="marker detection video">
    <p>数値データ: <code>/status</code></p>
  </main>
</body>
</html>
""")


@app.route("/status")
def status():
    with state_lock:
        cmd = latest_command
        marker_found = latest_marker_found
        processing_ms = latest_processing_ms

    return jsonify({
        "marker_found": marker_found,
        "left_pwm": 0 if cmd is None else cmd.left_pwm,
        "right_pwm": 0 if cmd is None else cmd.right_pwm,
        "strength": 0.0 if cmd is None else cmd.strength,
        "theta_deg": 0.0 if cmd is None else cmd.theta_deg,
        "processing_ms": processing_ms,
    })


def generate_mjpeg():
    while True:
        with state_lock:
            frame = None if latest_frame is None else latest_frame.copy()

        if frame is not None:
            encoded, jpeg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if encoded:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )

        time.sleep(WEB_INTERVAL_SEC)


@app.route("/video")
def video():
    return Response(
        generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def main():
    vision_thread = threading.Thread(target=vision_loop, daemon=True)
    vision_thread.start()
    print(f"web server listening on http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


if __name__ == "__main__":
    main()
