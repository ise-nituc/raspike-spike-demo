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
- ぬいぐるみを画面の上／下へ動かす: 前進／後退
- 赤→緑の向きを画面の右／左へひねる: 右／左旋回
"""

import os
import time
import math
import socket
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string, request
from picamera2 import Picamera2


# ============================================================
# 基本設定
# ============================================================

WIDTH = 320
HEIGHT = 240

# モータ出力設定
PWM_MAX = 100

# Web画面から調整するモータ出力倍率。計算値は最終的に PWM_MAX で制限する。
SPEED_GAIN_DEFAULT = float(os.environ.get("RASPIKE_SPEED_GAIN", "1.5"))
SPEED_GAIN_MIN = 0.5
SPEED_GAIN_MAX = 6.0

# 操作領域設定
# 画像中心からこの距離まで離すと最大操作量になる
ACTIVE_RADIUS = min(WIDTH, HEIGHT) * 0.40

# 中心付近の停止領域
DEADZONE_DEFAULT = float(os.environ.get("RASPIKE_DEADZONE", "0.05"))
DEADZONE_MIN = 0.0
DEADZONE_MAX = 0.30


STOP_MODE_DISABLED = 0
STOP_MODE_REFLECTION = 1
STOP_MODE_RGB = 2
SENSOR_RGB_MIN = 0
SENSOR_RGB_MAX = 1023
RGB_STOP_DEFAULTS = {
    "r_min": 0, "r_max": 350,
    "g_min": 150, "g_max": 1023,
    "b_min": 0, "b_max": 450,
}
# 走行体の黒線停止に使うカラーセンサー反射光の閾値（0〜100）。
BLACK_THRESHOLD_DEFAULT = int(os.environ.get("RASPIKE_BLACK_THRESHOLD", "8"))
BLACK_THRESHOLD_MIN = 0
BLACK_THRESHOLD_MAX = 100

# 正面付近では意図しない旋回を抑える（sin(theta) に対する比率）
TURN_DEADZONE = 0.10

# 操作量カーブ
# 1.0: 線形
# 1.0未満: デッドゾーンを出た直後から操作量を大きめにする
GAMMA = 0.7

# 旋回の効き
TURN_GAIN = 1.0

# 検出面積の最小値
MIN_RED_AREA = 80
MIN_GREEN_AREA = 80

# 赤と緑の重心が近すぎる場合は向きが不安定なので無効にする
MIN_MARKER_DISTANCE = 20.0

# Webサーバ設定
WEB_HOST = "0.0.0.0"
WEB_PORT = int(os.environ.get("RASPIKE_WEB_PORT", "8081"))
WEB_INTERVAL_SEC = 0.1
JPEG_QUALITY = 70

# RasPike-ARTは同じRaspberry Pi上で動作するため、TCPはローカルだけで待ち受ける
TCP_HOST = "127.0.0.1"
TCP_PORT = 65432


latest_frame = None
latest_command = None
latest_marker_found = False
latest_processing_ms = 0.0
latest_control_enabled = None
latest_black_stop = None
latest_robot_status_time = 0.0
latest_speed_gain = max(SPEED_GAIN_MIN, min(SPEED_GAIN_DEFAULT, SPEED_GAIN_MAX))
latest_deadzone = max(DEADZONE_MIN, min(DEADZONE_DEFAULT, DEADZONE_MAX))

# 操縦アルゴリズム
# legacy   : 前後=マーカー中心の上下、旋回=赤→緑の向き（従来方式）
# centroid : 前後=マーカー中心の上下、旋回=マーカー中心の左右（ジョイスティック方式）
CONTROL_MODE_LEGACY = "legacy"
CONTROL_MODE_CENTROID = "centroid"
CONTROL_MODES = {CONTROL_MODE_LEGACY, CONTROL_MODE_CENTROID}
latest_control_mode = os.environ.get("RASPIKE_CONTROL_MODE", CONTROL_MODE_LEGACY)
if latest_control_mode not in CONTROL_MODES:
    latest_control_mode = CONTROL_MODE_LEGACY
latest_black_threshold = max(
    BLACK_THRESHOLD_MIN, min(BLACK_THRESHOLD_DEFAULT, BLACK_THRESHOLD_MAX)
)
latest_robot_left_pwm = None
latest_robot_right_pwm = None
latest_sensor_rgb = None
latest_stop_mode = STOP_MODE_REFLECTION
latest_rgb_stop = RGB_STOP_DEFAULTS.copy()
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


def orient_camera_frame(frame_bgr):
    """機体前方が画面上になるよう、カメラ画像を上下反転する。"""
    return cv2.flip(frame_bgr, 0)


def apply_deadzone(value, deadzone):
    """符号を保ったままデッドゾーンを除き、残りを 0〜1 に再正規化する。"""
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = (magnitude - deadzone) / (1.0 - deadzone)
    return math.copysign(scaled, value)


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

def calculate_motor_command(
    marker, speed_gain=SPEED_GAIN_DEFAULT, deadzone=DEADZONE_DEFAULT
):
    """
    マーカー状態から left_pwm / right_pwm を計算する。
    """

    image_cy = HEIGHT / 2.0

    # 画像中心からマーカー中心までの前後方向のずれ。
    # orient_camera_frame() 後は画面上が機体前方となる。
    dy = image_cy - marker.cy  # 上を正にする

    # 前進・後退はマーカー中心の前後位置だけで決める。横へずらしても
    # 速度が上がらないため、ぬいぐるみをカメラへ厳密に合わせる必要がない。
    forward_ratio = clip(dy / ACTIVE_RADIUS, -1.0, 1.0)
    forward = apply_deadzone(forward_ratio, deadzone)
    forward = math.copysign(abs(forward) ** GAMMA, forward) if forward else 0.0

    # 旋回は赤→緑の向きだけで決める。中心位置に関係なく、ぬいぐるみを
    # その場でひねる操作にロボットが追従する。
    turn = apply_deadzone(math.sin(marker.theta), TURN_DEADZONE)
    strength = max(abs(forward), abs(turn))

    # 差動二輪への変換
    # 右旋回は左を正、右を負にする。前後成分とは独立しているため、
    # マーカーが中央にあっても left=+N, right=-N のその場旋回になる。
    left = speed_gain * (forward + TURN_GAIN * turn)
    right = speed_gain * (forward - TURN_GAIN * turn)

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
        distance_ratio=abs(forward_ratio),
        theta_deg=angle_deg(marker.theta),
    )


def calculate_motor_command_centroid(
    marker, speed_gain=SPEED_GAIN_DEFAULT, deadzone=DEADZONE_DEFAULT
):
    """
    マーカー中心を2軸ジョイスティックとして扱う操縦方式。

    - 上下方向のずれ -> 前進／後退
    - 左右方向のずれ -> 左／右旋回

    赤→緑の向き(theta)は操縦には使わない。
    """
    image_cx = WIDTH / 2.0
    image_cy = HEIGHT / 2.0

    # 画面上を前進、画面右を右旋回とする。
    dx = marker.cx - image_cx
    dy = image_cy - marker.cy

    forward_ratio = clip(dy / ACTIVE_RADIUS, -1.0, 1.0)
    turn_ratio = clip(dx / ACTIVE_RADIUS, -1.0, 1.0)

    forward = apply_deadzone(forward_ratio, deadzone)
    turn = apply_deadzone(turn_ratio, TURN_DEADZONE)

    # 中央を出た直後から反応しやすくする既存カーブを両軸に適用。
    forward = math.copysign(abs(forward) ** GAMMA, forward) if forward else 0.0
    turn = math.copysign(abs(turn) ** GAMMA, turn) if turn else 0.0

    strength = max(abs(forward), abs(turn))

    left = speed_gain * (forward + TURN_GAIN * turn)
    right = speed_gain * (forward - TURN_GAIN * turn)
    left, right = normalize_motor_pair(left, right)

    return MotorCommand(
        left_pwm=int(round(PWM_MAX * left)),
        right_pwm=int(round(PWM_MAX * right)),
        strength=strength,
        forward=forward,
        turn=turn,
        distance_ratio=min(1.0, math.hypot(dx, dy) / ACTIVE_RADIUS),
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
# RasPike-ART向けTCPサーバ
# ============================================================

def get_latest_motor_command_text(include_stop_config=False):
    """最新の左右PWM値と、必要なら緊急停止設定を返す。"""
    with state_lock:
        cmd = latest_command
        black_threshold = latest_black_threshold
        stop_mode = latest_stop_mode
        rgb_stop = latest_rgb_stop.copy()

    pwm_text = "0:0" if cmd is None else f"{cmd.left_pwm}:{cmd.right_pwm}"
    if include_stop_config:
        return (
            f"{pwm_text}:{stop_mode}:{black_threshold}"
            f":{rgb_stop['r_min']}:{rgb_stop['r_max']}"
            f":{rgb_stop['g_min']}:{rgb_stop['g_max']}"
            f":{rgb_stop['b_min']}:{rgb_stop['b_max']}\n"
        )
    return f"{pwm_text}\n"


def handle_tcp_client(conn, addr):
    """新旧PWMクライアントへ応答し、ロボット状態を保存する。"""
    global latest_control_enabled
    global latest_black_stop
    global latest_robot_status_time
    global latest_robot_left_pwm
    global latest_robot_right_pwm
    global latest_sensor_rgb

    print(f"TCP client connected: {addr}")
    receive_buffer = b""
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                return
            receive_buffer += data

            while b"\n" in receive_buffer:
                request_line, receive_buffer = receive_buffer.split(b"\n", 1)
                request = request_line.decode(errors="ignore").strip()
                parts = request.split()

                if (
                    len(parts) in {3, 5, 8}
                    and parts[0] == "GET"
                    and parts[1] in {"0", "1"}
                    and parts[2] in {"0", "1"}
                ):
                    try:
                        numeric_status = [int(value) for value in parts[3:]]
                    except ValueError:
                        response = "ERROR invalid robot status\n"
                        conn.sendall(response.encode())
                        continue

                    with state_lock:
                        latest_control_enabled = parts[1] == "1"
                        latest_black_stop = parts[2] == "1"
                        if len(parts) >= 5:
                            latest_robot_left_pwm = numeric_status[0]
                            latest_robot_right_pwm = numeric_status[1]
                        if len(parts) == 8:
                            latest_sensor_rgb = tuple(numeric_status[2:5])
                        latest_robot_status_time = time.monotonic()
                    response = get_latest_motor_command_text(
                        include_stop_config=len(parts) >= 5
                    )
                elif request == "GET":
                    response = get_latest_motor_command_text()
                else:
                    response = "ERROR unknown command\n"

                conn.sendall(response.encode())


def tcp_server_loop():
    """同じRaspberry Pi上のRasPike-ART向けTCPサーバ。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((TCP_HOST, TCP_PORT))
        server_socket.listen()

        print(f"motor command TCP server listening on {TCP_HOST}:{TCP_PORT}")

        while True:
            conn, addr = server_socket.accept()
            try:
                handle_tcp_client(conn, addr)
            except (ConnectionError, OSError) as error:
                # クライアントが異常切断しても待受スレッドは継続する。
                print(f"TCP client disconnected with error: {error}")


# ============================================================
# 描画
# ============================================================

def draw_debug_view(frame_bgr, marker, cmd, processing_ms, deadzone=DEADZONE_DEFAULT):
    view = frame_bgr.copy()

    image_cx = int(WIDTH / 2)
    image_cy = int(HEIGHT / 2)

    # 画像中心とデッドゾーン。以前の大きな有効半径の円は停止範囲との
    # 誤解を招くため表示せず、青い円を実際の停止範囲だけにする。
    cv2.circle(view, (image_cx, image_cy), 3, (255, 255, 255), -1)
    cv2.circle(
        view,
        (image_cx, image_cy),
        int(ACTIVE_RADIUS * deadzone),
        (255, 0, 0),
        2
    )

    if marker is None:
        # 未検出時の案内はWeb UI側で、子ども向けの柔らかい日本語で表示する。
        # 映像には警告文を重ねず、カメラの様子を確認しやすくしておく。
        pass
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


def make_marker_only_frame(frame_bgr, marker):
    """Web表示用に、検出した赤・緑マーカー以外を黒く隠す。"""
    marker_mask = np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
    if marker is not None:
        cv2.drawContours(
            marker_mask,
            [marker.red.contour, marker.green.contour],
            -1,
            255,
            cv2.FILLED,
        )
    return cv2.bitwise_and(frame_bgr, frame_bgr, mask=marker_mask)


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
            # Picamera2/libcamera の RGB888 は、capture_array() では
            # OpenCV が期待する B, G, R の順に並ぶ。
            "format": "RGB888",
        }
    )

    picam2.configure(config)
    picam2.start()

    # 露出やホワイトバランスが落ち着くのを待つ
    time.sleep(1.0)

    print("marker detection started")

    try:
        while True:
            loop_t0 = time.perf_counter()

            # RGB888 というフォーマット名に反して、配列のチャンネル順は
            # OpenCV と同じ BGR。RGB とみなして入れ替えると赤と青が反転する。
            frame_bgr = orient_camera_frame(picam2.capture_array())

            marker, red_mask, green_mask = detect_marker(frame_bgr)

            with state_lock:
                speed_gain = latest_speed_gain
                deadzone = latest_deadzone
                control_mode = latest_control_mode

            if marker is not None:
                if control_mode == CONTROL_MODE_CENTROID:
                    cmd = calculate_motor_command_centroid(marker, speed_gain, deadzone)
                else:
                    cmd = calculate_motor_command(marker, speed_gain, deadzone)
            else:
                # どちらかのマーカーを見失ったら、直前値を保持せず即停止する。
                cmd = stop_command()

            send_motor_command(cmd)

            processing_ms = (time.perf_counter() - loop_t0) * 1000.0
            privacy_frame = make_marker_only_frame(frame_bgr, marker)
            view = draw_debug_view(
                privacy_frame, marker, cmd, processing_ms, deadzone
            )

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
  <title>ぬいぐるみロボット おさんぽ中！</title>
  <style>
    :root {
      --cream: #fffaf0; --paper: #fffef9; --ink: #263936;
      --green: #2f9b68; --green-soft: #dff4e8; --blue: #3289bd;
      --blue-soft: #e1f3fb; --orange: #ee8b3a; --orange-soft: #fff0dc;
      --muted: #65746f; --line: #e9e1d1; --shadow: 0 10px 30px rgba(62, 77, 67, .09);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; color: var(--ink); background: var(--cream);
      font-family: "Hiragino Maru Gothic ProN", "Yu Gothic", Meiryo, sans-serif;
    }
    body::before {
      content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .35;
      background-image: radial-gradient(#e9bd72 1px, transparent 1px);
      background-size: 24px 24px;
    }
    .page { position: relative; width: min(1180px, calc(100% - 32px)); margin: auto; padding: 28px 0 42px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
    .event { margin: 0 0 6px; color: var(--green); font-weight: 800; letter-spacing: .08em; }
    h1 { margin: 0; font-size: clamp(1.75rem, 4vw, 3rem); line-height: 1.2; letter-spacing: .03em; }
    .live { display: flex; align-items: center; gap: 9px; flex: none; padding: 10px 16px; border-radius: 999px; background: white; box-shadow: var(--shadow); font-weight: 800; }
    .live-dot { width: 11px; height: 11px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 5px var(--green-soft); }
    .live.offline .live-dot { background: #a1aaa6; box-shadow: 0 0 0 5px #edf0ee; }
    .dashboard { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(290px, .85fr); gap: 22px; align-items: stretch; }
    .panel, .status-card, details { background: var(--paper); border: 1px solid rgba(222, 211, 192, .8); box-shadow: var(--shadow); }
    .panel { padding: 14px; border-radius: 26px; }
    .video-wrap { position: relative; overflow: hidden; border-radius: 18px; background: #dce6df; aspect-ratio: 4 / 3; }
    .video-wrap img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .camera-label { position: absolute; left: 13px; bottom: 12px; padding: 7px 11px; border-radius: 999px; color: white; background: rgba(25, 46, 39, .76); font-size: .83rem; font-weight: 700; backdrop-filter: blur(4px); }
    .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .status-card { min-height: 132px; padding: 17px; border-radius: 20px; overflow: hidden; transition: transform .2s, background-color .25s; }
    .status-card.changed { animation: card-pop .36s ease-out; }
    @keyframes card-pop { 45% { transform: translateY(-3px) scale(1.015); } }
    .status-card.detect { grid-column: 1 / -1; min-height: 154px; background: var(--green-soft); }
    .status-card.direction { background: var(--blue-soft); }
    .status-card.speed { background: var(--orange-soft); }
    .status-card.motion { grid-column: 1 / -1; min-height: 112px; }
    .status-card.control { background: #edf0ee; }
    .status-card.control.enabled { background: var(--green-soft); }
    .status-card.safety { background: #edf0ee; }
    .status-card.safety.active { background: #fbe2df; }
    .status-card.safety.active .card-value { color: #a83a32; }
    .tuning { grid-column: 1 / -1; padding: 18px; border-radius: 20px; background: #f2ecff; }
    .tuning-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
    .tuning-title { margin: 0; font-size: 1.05rem; font-weight: 900; }
    .gain-value { color: #7048a8; font-size: 1.35rem; font-weight: 900; }
    .gain-slider { width: 100%; margin: 14px 0 6px; accent-color: #7048a8; }
    .pwm-readout { margin: 9px 0 0; font-family: ui-monospace, Consolas, monospace; font-weight: 800; }
    .card-label { margin: 0 0 10px; color: var(--muted); font-size: .83rem; font-weight: 800; }
    .card-value { margin: 0; font-size: clamp(1.35rem, 2.5vw, 2rem); font-weight: 900; line-height: 1.2; }
    .detect .card-value { color: #19784c; }
    .card-note { margin: 8px 0 0; color: var(--muted); font-size: .9rem; line-height: 1.5; }
    .icon { float: right; font-size: 2rem; line-height: 1; }
    .about { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 18px; margin: 26px 0; padding: 18px 22px; border-radius: 20px; background: #fff; box-shadow: var(--shadow); }
    .about p { margin: 0; line-height: 1.65; font-size: .95rem; }
    .about strong { color: var(--blue); }
    .flow-arrow { color: var(--orange); font-size: 1.5rem; font-weight: 900; }
    details { border-radius: 20px; overflow: hidden; }
    summary { cursor: pointer; padding: 18px 22px; color: var(--blue); font-weight: 900; list-style: none; }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: "＋"; float: right; }
    details[open] summary::after { content: "−"; }
    .data-body { border-top: 1px solid var(--line); padding: 18px 22px 22px; }
    .data-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
    .datum { min-width: 0; padding: 12px; border-radius: 13px; background: #f6f4ed; }
    .datum dt { margin-bottom: 5px; color: var(--muted); font-size: .72rem; overflow-wrap: anywhere; }
    .datum dd { margin: 0; font-family: ui-monospace, Consolas, monospace; font-size: 1rem; font-weight: 800; }
    .debug-note { margin: 14px 0 0; color: var(--muted); font-size: .8rem; }
    .stop-mode { width: 100%; margin: 8px 0; padding: 8px; border: 1px solid var(--line); border-radius: 8px; }
    .stop-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }
    .stop-grid label { color: var(--muted); font-size: .75rem; }
    .stop-grid input { width: 100%; padding: 7px; border: 1px solid var(--line); border-radius: 7px; }
    @media (max-width: 850px) {
      .dashboard { grid-template-columns: 1fr; }
      .data-grid { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 540px) {
      .page { width: min(100% - 20px, 1180px); padding-top: 18px; }
      header { align-items: flex-start; } .live { padding: 8px 11px; font-size: .78rem; }
      .panel { padding: 9px; border-radius: 20px; }
      .status-card { min-height: 118px; padding: 14px; }
      .about { grid-template-columns: 1fr; gap: 8px; } .flow-arrow { transform: rotate(90deg); justify-self: center; }
      .data-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (prefers-reduced-motion: reduce) { .status-card.changed { animation: none; } }
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div><p class="event">こども科学館inときわ</p><h1>ぬいぐるみロボット<br>おさんぽ中！</h1></div>
      <div id="connection" class="live"><span class="live-dot"></span><span>つながっています</span></div>
    </header>

    <section class="dashboard" aria-label="ロボットのライブ映像と状態">
      <div class="panel">
        <div class="video-wrap"><img src="/video" alt="ロボット上部のカメラ映像"><span class="camera-label">カメラが見ているところ</span></div>
      </div>
      <div class="status-grid" aria-live="polite">
        <article id="detect-card" class="status-card detect"><span class="icon" aria-hidden="true">●</span><p class="card-label">ぬいぐるみ</p><p id="detect" class="card-value">さがしています…</p><p id="detect-note" class="card-note">カメラの上にもどしてね</p></article>
        <article id="direction-card" class="status-card direction"><span id="direction-icon" class="icon" aria-hidden="true">↑</span><p class="card-label">すすむ向き</p><p id="direction" class="card-value">—</p></article>
        <article id="speed-card" class="status-card speed"><span class="icon" aria-hidden="true">⚡</span><p class="card-label">スピード</p><p id="speed" class="card-value">—</p></article>
        <article id="motion-card" class="status-card motion"><span id="motion-icon" class="icon" aria-hidden="true">■</span><p class="card-label">ロボット</p><p id="motion" class="card-value">ストップ！</p><p id="motion-note" class="card-note">ぬいぐるみを待っています</p></article>
        <article id="control-card" class="status-card control"><span id="control-icon" class="icon" aria-hidden="true">—</span><p class="card-label">フォースセンサ</p><p id="control" class="card-value">状態不明</p><p id="control-note" class="card-note">ロボットからの通信を待っています</p></article>
        <article id="safety-card" class="status-card safety"><span id="safety-icon" class="icon" aria-hidden="true">—</span><p class="card-label">緊急停止センサ</p><p id="safety" class="card-value">状態不明</p><p id="safety-note" class="card-note">ロボットからの通信を待っています</p></article>
        <section class="status-card tuning" aria-labelledby="gain-title">
          <label for="control-mode" class="tuning-title">操縦アルゴリズム</label>
          <select id="control-mode" class="stop-mode">
            <option value="legacy">従来方式（赤→緑の向きで旋回）</option>
            <option value="centroid">重心追従（重心の左右位置で旋回）</option>
          </select>
          <p class="card-note">動作確認済みの従来方式を残したまま、重心追従を切り替えて試せます。</p>
          <div class="tuning-head"><h2 id="gain-title" class="tuning-title">モータ感度</h2><output id="gain-value" class="gain-value" for="gain">1.50 倍</output></div>
          <input id="gain" class="gain-slider" type="range" min="0.5" max="6.0" step="0.1" value="1.5" aria-describedby="gain-note">
          <p id="gain-note" class="card-note">大きくすると、同じぬいぐるみ操作でもモータ指令が強くなります。</p>
          <div class="tuning-head"><label for="deadzone" class="tuning-title">中央の停止範囲</label><output id="deadzone-value" class="gain-value" for="deadzone">5%</output></div>
          <input id="deadzone" class="gain-slider" type="range" min="0" max="0.30" step="0.01" value="0.05">
          <p class="card-note">小さくすると、中央から少し動かしただけで前進・後退します。</p>
          <div class="tuning-head"><label for="black-threshold" class="tuning-title">黒線の判定値</label><output id="black-threshold-value" class="gain-value" for="black-threshold">8</output></div>
          <input id="black-threshold" class="gain-slider" type="range" min="0" max="100" step="1" value="8">
          <p class="card-note">薄茶色で停止する場合は小さくします。小さすぎると黒線を見逃すため、実際の床で確認してください。</p>
          <label for="stop-mode" class="tuning-title">緊急停止の条件</label>
          <select id="stop-mode" class="stop-mode">
            <option value="0">無効</option><option value="1">反射率（黒）</option><option value="2">RGB範囲</option>
          </select>
          <div class="stop-grid">
            <label>R 最小<input id="r-min" type="number" min="0" max="1023"></label>
            <label>R 最大<input id="r-max" type="number" min="0" max="1023"></label>
            <label>G 最小<input id="g-min" type="number" min="0" max="1023"></label>
            <label>G 最大<input id="g-max" type="number" min="0" max="1023"></label>
            <label>B 最小<input id="b-min" type="number" min="0" max="1023"></label>
            <label>B 最大<input id="b-max" type="number" min="0" max="1023"></label>
          </div>
          <p id="sensor-rgb" class="pwm-readout">現在のRGB: 通信待ち</p>
          <p id="pwm-readout" class="pwm-readout">計算PWM: L=0 / R=0</p>
          <p id="robot-pwm-readout" class="pwm-readout">ロボット適用PWM: 通信待ち</p>
          <p class="card-note">※ 計算した指令値です。モータが実際に回転したことを検知する表示ではありません。</p>
        </section>
      </div>
    </section>

    <section class="about" aria-label="ロボットの仕組み">
      <p><strong>カメラ</strong>が、ぬいぐるみの底の<br>赤と緑のマーカーを見ています。</p><span class="flow-arrow" aria-hidden="true">→</span><p><strong>Raspberry Pi</strong>が画像を解析し、<br>SPIKE Primeがモーターを動かします。</p>
    </section>

    <details>
      <summary>しくみ・データを見る</summary>
      <div class="data-body">
        <dl class="data-grid">
          <div class="datum"><dt>marker_found</dt><dd id="raw-marker">—</dd></div>
          <div class="datum"><dt>left_pwm</dt><dd id="raw-left">—</dd></div>
          <div class="datum"><dt>right_pwm</dt><dd id="raw-right">—</dd></div>
          <div class="datum"><dt>strength</dt><dd id="raw-strength">—</dd></div>
          <div class="datum"><dt>theta_deg</dt><dd id="raw-theta">—</dd></div>
          <div class="datum"><dt>processing_ms</dt><dd id="raw-processing">—</dd></div>
          <div class="datum"><dt>control_enabled</dt><dd id="raw-control">—</dd></div>
          <div class="datum"><dt>black_stop</dt><dd id="raw-black-stop">—</dd></div>
        </dl>
        <p class="debug-note">左右のPWMはモーターへの指令値、strengthは操作の強さ、theta_degはマーカーの向き、processing_msは画像1枚の解析時間です。</p>
      </div>
    </details>
  </main>
  <script>
    (() => {
      const $ = id => document.getElementById(id);
      let previous = {};
      let settingsEditing = false, settingsTimer;
      const setCard = (id, value) => {
        const el = $(id); if (el.textContent === value) return;
        el.textContent = value; const card = $(id + '-card');
        if (card) { card.classList.remove('changed'); void card.offsetWidth; card.classList.add('changed'); }
      };
      const number = (value, digits) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—';
      const direction = (forward, turn) => {
        const f = Number(forward) || 0, t = Number(turn) || 0;
        if (Math.abs(f) < 0.05 && Math.abs(t) < 0.05) return ['まんなか', '●'];
        if (Math.abs(t) > Math.abs(f)) return t > 0 ? ['みぎ', '→'] : ['ひだり', '←'];
        return f >= 0 ? ['まっすぐ', '↑'] : ['うしろ', '↓'];
      };
      async function update() {
        try {
          const response = await fetch('/status', { cache: 'no-store' });
          if (!response.ok) throw new Error(response.status);
          const data = await response.json();
          const found = data.marker_found === true;
          const left = Number(data.left_pwm) || 0, right = Number(data.right_pwm) || 0;
          const robotFresh = data.robot_status_fresh === true;
          const controlEnabled = robotFresh && data.control_enabled === true;
          const blackStop = robotFresh && data.black_stop === true;
          const moving = Math.max(Math.abs(left), Math.abs(right)) > 1 && controlEnabled && !blackStop;
          const strength = Math.max(Math.abs(left), Math.abs(right)) / (Number(data.pwm_max) || 100);
          const [directionText, directionIcon] = direction(data.forward, data.turn);

          setCard('detect', found ? 'みつけたよ！' : 'さがしています…');
          $('detect-note').textContent = found ? 'ぬいぐるみの動きが見えています' : 'カメラの上にもどしてね';
          setCard('direction', found ? directionText : '—'); $('direction-icon').textContent = found ? directionIcon : '·';
          setCard('speed', !found || !moving ? 'おやすみ' : strength < .34 ? 'ゆっくり' : strength < .72 ? 'いい感じ' : 'はやい！');
          setCard('motion', moving ? '走行中！' : 'ストップ！');
          $('motion-note').textContent = moving ? 'ぬいぐるみといっしょに動いています' : found ? 'まんなかでひとやすみ' : 'ぬいぐるみを待っています';
          $('motion-icon').textContent = moving ? '▶' : '■';

          setCard('control', robotFresh ? (controlEnabled ? '追従 ON' : '追従 OFF') : '状態不明');
          $('control-note').textContent = robotFresh ? (controlEnabled ? 'マーカーに従って走行できます' : 'フォースセンサで停止中です') : 'ロボットからの通信を待っています';
          $('control-icon').textContent = robotFresh ? (controlEnabled ? '▶' : '■') : '—';
          $('control-card').classList.toggle('enabled', controlEnabled);
          setCard('safety', robotFresh ? (blackStop ? '作動中！' : '解除') : '状態不明');
          $('safety-note').textContent = robotFresh ? (blackStop ? '設定した色・明るさを検知して停止中です' : '停止条件は検知していません') : 'ロボットからの通信を待っています';
          $('safety-icon').textContent = robotFresh ? (blackStop ? '●' : '○') : '—';
          $('safety-card').classList.toggle('active', blackStop);

          $('raw-marker').textContent = String(data.marker_found);
          $('raw-left').textContent = String(data.left_pwm); $('raw-right').textContent = String(data.right_pwm);
          $('raw-strength').textContent = number(data.strength, 3); $('raw-theta').textContent = number(data.theta_deg, 1);
          $('raw-processing').textContent = number(data.processing_ms, 1) + (Number.isFinite(Number(data.processing_ms)) ? ' ms' : '');
          $('raw-control').textContent = robotFresh ? String(data.control_enabled) : '—';
          $('raw-black-stop').textContent = robotFresh ? String(data.black_stop) : '—';
          $('pwm-readout').textContent = `計算PWM: L=${left} / R=${right}`;
          const robotLeft = Number(data.robot_left_pwm), robotRight = Number(data.robot_right_pwm);
          $('robot-pwm-readout').textContent = robotFresh && Number.isFinite(robotLeft) && Number.isFinite(robotRight)
            ? `ロボット適用PWM: L=${robotLeft} / R=${robotRight}` : 'ロボット適用PWM: 通信待ち';
          const rgb = data.sensor_rgb;
          $('sensor-rgb').textContent = robotFresh && rgb ? `現在のRGB: R=${rgb[0]} G=${rgb[1]} B=${rgb[2]}` : '現在のRGB: 通信待ち';
          if (!settingsEditing) {
            $('control-mode').value = String(data.control_mode || 'legacy');
            $('gain').value = Number(data.speed_gain).toFixed(1);
            $('gain-value').textContent = Number(data.speed_gain).toFixed(2) + ' 倍';
            $('deadzone').value = Number(data.deadzone).toFixed(2);
            $('deadzone-value').textContent = Math.round(Number(data.deadzone) * 100) + '%';
            $('black-threshold').value = String(data.black_threshold);
            $('black-threshold-value').textContent = String(data.black_threshold);
            $('stop-mode').value = String(data.stop_mode);
            for (const name of ['r_min','r_max','g_min','g_max','b_min','b_max']) {
              $(name.replace('_','-')).value = String(data.rgb_stop[name]);
            }
          }
          $('connection').classList.remove('offline'); $('connection').lastElementChild.textContent = 'つながっています';
          previous = data;
        } catch (error) {
          $('connection').classList.add('offline'); $('connection').lastElementChild.textContent = 'つなぎ直しています…';
        }
      }
      const saveSettings = async () => {
        const gain = Number($('gain').value), deadzone = Number($('deadzone').value);
        const blackThreshold = Number($('black-threshold').value);
        const payload = {
          control_mode: $('control-mode').value,
          speed_gain: gain, deadzone, black_threshold: blackThreshold,
          stop_mode: Number($('stop-mode').value)
        };
        for (const name of ['r_min','r_max','g_min','g_max','b_min','b_max']) {
          payload[name] = Number($(name.replace('_','-')).value);
        }
        $('gain-value').textContent = gain.toFixed(2) + ' 倍';
        $('deadzone-value').textContent = Math.round(deadzone * 100) + '%';
        $('black-threshold-value').textContent = String(blackThreshold);
        clearTimeout(settingsTimer);
        settingsTimer = setTimeout(async () => {
          try {
            const response = await fetch('/settings', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error(response.status);
          } finally { settingsEditing = false; }
        }, 180);
      };
      for (const id of ['control-mode','gain','deadzone','black-threshold','stop-mode','r-min','r-max','g-min','g-max','b-min','b-max']) {
        $(id).addEventListener('input', () => { settingsEditing = true; saveSettings(); });
      }
      update(); setInterval(update, 600);
    })();
  </script>
</body>
</html>
""")


@app.route("/status")
def status():
    with state_lock:
        cmd = latest_command
        marker_found = latest_marker_found
        processing_ms = latest_processing_ms
        control_enabled = latest_control_enabled
        black_stop = latest_black_stop
        robot_status_time = latest_robot_status_time
        speed_gain = latest_speed_gain
        deadzone = latest_deadzone
        control_mode = latest_control_mode
        robot_left_pwm = latest_robot_left_pwm
        robot_right_pwm = latest_robot_right_pwm
        black_threshold = latest_black_threshold
        stop_mode = latest_stop_mode
        rgb_stop = latest_rgb_stop.copy()
        sensor_rgb = latest_sensor_rgb

    robot_status_fresh = time.monotonic() - robot_status_time <= 1.0

    return jsonify({
        "marker_found": marker_found,
        "left_pwm": 0 if cmd is None else cmd.left_pwm,
        "right_pwm": 0 if cmd is None else cmd.right_pwm,
        "strength": 0.0 if cmd is None else cmd.strength,
        "forward": 0.0 if cmd is None else cmd.forward,
        "turn": 0.0 if cmd is None else cmd.turn,
        "theta_deg": 0.0 if cmd is None else cmd.theta_deg,
        "processing_ms": processing_ms,
        "control_enabled": control_enabled if robot_status_fresh else None,
        "black_stop": black_stop if robot_status_fresh else None,
        "robot_status_fresh": robot_status_fresh,
        "speed_gain": speed_gain,
        "control_mode": control_mode,
        "pwm_max": PWM_MAX,
        "deadzone": deadzone,
        "robot_left_pwm": robot_left_pwm if robot_status_fresh else None,
        "robot_right_pwm": robot_right_pwm if robot_status_fresh else None,
        "black_threshold": black_threshold,
        "stop_mode": stop_mode,
        "rgb_stop": rgb_stop,
        "sensor_rgb": sensor_rgb if robot_status_fresh else None,
    })


@app.post("/settings")
def settings():
    """Web画面から走行と緊急停止の設定を更新する。"""
    payload = request.get_json(silent=True) or {}
    supported = {
        "control_mode", "speed_gain", "deadzone", "black_threshold", "stop_mode",
        "r_min", "r_max", "g_min", "g_max", "b_min", "b_max",
    }
    if not (supported & payload.keys()):
        return jsonify({"error": "no supported setting supplied"}), 400

    def validated_number(name, current, low, high):
        if name not in payload:
            return current
        try:
            value = float(payload[name])
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        return clip(value, low, high)

    global latest_control_mode
    global latest_speed_gain
    global latest_deadzone
    global latest_black_threshold
    global latest_stop_mode
    global latest_rgb_stop
    with state_lock:
        try:
            control_mode = payload.get("control_mode", latest_control_mode)
            if control_mode not in CONTROL_MODES:
                raise ValueError("control_mode must be legacy or centroid")
            speed_gain = validated_number(
                "speed_gain", latest_speed_gain, SPEED_GAIN_MIN, SPEED_GAIN_MAX
            )
            deadzone = validated_number(
                "deadzone", latest_deadzone, DEADZONE_MIN, DEADZONE_MAX
            )
            black_threshold = int(round(validated_number(
                "black_threshold", latest_black_threshold,
                BLACK_THRESHOLD_MIN, BLACK_THRESHOLD_MAX,
            )))
            stop_mode = int(round(validated_number(
                "stop_mode", latest_stop_mode,
                STOP_MODE_DISABLED, STOP_MODE_RGB,
            )))
            rgb_stop = {
                name: int(round(validated_number(
                    name, latest_rgb_stop[name], SENSOR_RGB_MIN, SENSOR_RGB_MAX
                )))
                for name in RGB_STOP_DEFAULTS
            }
            for color in ("r", "g", "b"):
                if rgb_stop[f"{color}_min"] > rgb_stop[f"{color}_max"]:
                    raise ValueError(f"{color}_min must be <= {color}_max")
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        latest_control_mode = control_mode
        latest_speed_gain = speed_gain
        latest_deadzone = deadzone
        latest_black_threshold = black_threshold
        latest_stop_mode = stop_mode
        latest_rgb_stop = rgb_stop

    return jsonify({
        "control_mode": control_mode,
        "speed_gain": speed_gain,
        "deadzone": deadzone,
        "black_threshold": black_threshold,
        "stop_mode": stop_mode,
        "rgb_stop": rgb_stop,
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
    tcp_thread = threading.Thread(target=tcp_server_loop, daemon=True)
    vision_thread.start()
    tcp_thread.start()
    print(f"web server listening on http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


if __name__ == "__main__":
    main()
