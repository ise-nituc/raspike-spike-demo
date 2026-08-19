import os
import socket
import threading
import time

import cv2
from flask import Flask, Response, jsonify, render_template, request
from picamera2 import Picamera2

from detect_line import estimate_steering, draw_debug

from line_control import LineTraceSettings, calculate_motor_pwm, parse_pwm_request

HOST = "127.0.0.1"
PORT = 65432

WEB_HOST = "0.0.0.0"
WEB_PORT = int(os.environ.get("RASPIKE_WEB_PORT", "8080"))

# デモ時は False 推奨
DEBUG = False

# カメラ取得解像度
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# 画像認識周期
# 0.05 = 約20Hz。重ければ 0.1 にする。
VISION_INTERVAL_SEC = 0.05

# Web表示周期
# 0.1 = 約10fps
WEB_INTERVAL_SEC = 0.1

# Web表示用サイズ
WEB_WIDTH = 480
WEB_HEIGHT = 360

settings_store = LineTraceSettings(os.path.join(os.path.dirname(__file__), "line_trace_settings.json"))

# JPEG品質
JPEG_QUALITY = 60


latest_left_pwm = 0
latest_right_pwm = 0
latest_steering = 0.0
latest_confidence = 0.0
latest_count = 0
latest_time = 0.0
latest_debug_frame = None

lock = threading.Lock()

app = Flask(__name__)


def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


def vision_loop():
    """
    Raspberry Pi Camera Module から画像を取得し、
    ライン検出結果とデバッグ画像を更新し続ける。
    """
    global latest_steering
    global latest_confidence
    global latest_left_pwm
    global latest_right_pwm
    global latest_count
    global latest_time
    global latest_debug_frame

    picam2 = Picamera2()

    config = picam2.create_video_configuration(
        main={
            "size": (CAMERA_WIDTH, CAMERA_HEIGHT),
            "format": "BGR888",
        }
    )
    picam2.configure(config)
    picam2.start()

    # カメラ起動直後の安定待ち
    time.sleep(1.0)

    try:
        while True:
            frame = picam2.capture_array()
            current_settings = settings_store.get()

            if frame is None:
                steering = 0.0
                confidence = 0.0
                debug = None
            else:
                # frame は BGR888 なので、そのまま OpenCV 処理へ渡せる
                steering, confidence, debug_info = estimate_steering(
                    frame,
                    black_value=current_settings["black_value"],
                    white_value=current_settings["white_value"],
                    vector_gain=current_settings["vector_gain"],
                )
                debug = draw_debug(frame, steering, confidence, debug_info)

            left_pwm, right_pwm = calculate_motor_pwm(
                steering, confidence, current_settings
            )

            with lock:
                latest_steering = float(steering)
                latest_confidence = float(confidence)
                latest_left_pwm = left_pwm
                latest_right_pwm = right_pwm
                latest_count += 1
                latest_time = time.time()
                latest_debug_frame = debug

                count = latest_count

            debug_print(
                f"steering={steering:.3f}, "
                f"confidence={confidence:.3f}, "
                f"count={count}"
            )

            time.sleep(VISION_INTERVAL_SEC)

    finally:
        picam2.stop()


def get_latest_motor_command_text(include_stop_threshold=False):
    """direct_pwm_camera 用の最新制御値を返す。"""
    with lock:
        left_pwm = latest_left_pwm
        right_pwm = latest_right_pwm

    pwm_text = f"{left_pwm}:{right_pwm}"
    if include_stop_threshold:
        threshold = settings_store.get()["stop_reflection_threshold"]
        return f"{pwm_text}:{threshold}\n"
    return f"{pwm_text}\n"


def handle_client(conn, addr):
    """
    新クライアントの状態付きGETと、旧クライアントのGETの両方に応答する。
    """
    receive_buffer = b""

    with conn:
        conn.settimeout(1.0)

        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    return
                receive_buffer += data

                while b"\n" in receive_buffer:
                    request_line, receive_buffer = receive_buffer.split(b"\n", 1)
                    request_text = request_line.decode(errors="ignore").strip()
                    extended_response = parse_pwm_request(request_text)

                    if extended_response is None:
                        response = "ERROR unknown command\n"
                    else:
                        response = get_latest_motor_command_text(
                            include_stop_threshold=extended_response
                        )
                    conn.sendall(response.encode())

            except socket.timeout:
                continue
            except Exception as error:
                try:
                    conn.sendall(f"ERROR {error}\n".encode())
                except Exception:
                    pass
                return

def tcp_server_loop():
    """
    RasPike側プログラムからの問い合わせを受けるTCPサーバ。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"vision TCP server listening on {HOST}:{PORT}")

        while True:
            conn, addr = server_socket.accept()
            handle_client(conn, addr)


@app.route("/")
def index():
    return render_template("line_trace.html")


@app.route("/settings", methods=["GET", "POST"])
def line_trace_settings():
    if request.method == "GET":
        return jsonify(settings_store.get())
    try:
        values = settings_store.update(request.get_json(force=True) or {})
    except (ValueError, TypeError, OSError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(values)


@app.route("/status")
def status():
    with lock:
        result = {
            "steering": latest_steering,
            "confidence": latest_confidence,
            "left_pwm": latest_left_pwm,
            "right_pwm": latest_right_pwm,
            "count": latest_count,
            "timestamp": latest_time,
        }
    return jsonify(result)


@app.route("/video")
def video():
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def generate_mjpeg():
    """
    Webブラウザ向けにMJPEGを配信する。
    """
    while True:
        with lock:
            frame = None if latest_debug_frame is None else latest_debug_frame.copy()

        if frame is not None:
            # Web表示用に縮小して通信量とJPEGエンコード負荷を下げる
            frame = cv2.resize(frame, (WEB_WIDTH, WEB_HEIGHT))

            ret, jpeg = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )

            if ret:
                data = jpeg.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    data +
                    b"\r\n"
                )

        time.sleep(WEB_INTERVAL_SEC)


def web_server_loop():
    """
    PCのブラウザから確認するためのWebサーバ。
    """
    print(f"web server listening on http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


def main():
    settings_store.load()
    vision_thread = threading.Thread(target=vision_loop, daemon=True)
    tcp_thread = threading.Thread(target=tcp_server_loop, daemon=True)

    vision_thread.start()
    tcp_thread.start()

    web_server_loop()


if __name__ == "__main__":
    main()
