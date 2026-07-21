import socket
import threading
import time

import cv2
from flask import Flask, Response, render_template_string
from picamera2 import Picamera2

from detect_line import estimate_steering, draw_debug


HOST = "127.0.0.1"
PORT = 65432

WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

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

# JPEG品質
JPEG_QUALITY = 60


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

            if frame is None:
                steering = 0.0
                confidence = 0.0
                debug = None
            else:
                # frame は BGR888 なので、そのまま OpenCV 処理へ渡せる
                steering, confidence,debug_info = estimate_steering(frame)
                debug = draw_debug(frame, steering, confidence, debug_info)

            with lock:
                latest_steering = float(steering)
                latest_confidence = float(confidence)
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


def get_latest_result_text():
    """
    最新の判定値を1行テキストとして返す。
    形式:
        steering confidence count timestamp
    """
    with lock:
        steering = latest_steering
        confidence = latest_confidence
        count = latest_count
        timestamp = latest_time

    return f"{steering:.6f} {confidence:.6f} {count} {timestamp:.6f}\n"

def handle_client(conn, addr):
    """
    TCPクライアントからの問い合わせに応答する。
    RasPike側から "GET" を送ると最新の判定値を返す。
    接続は維持し、複数回のGETに応答する。
    """
    with conn:
        conn.settimeout(1.0)

        while True:
            try:
                data = conn.recv(1024)

                if not data:
                    return

                request = data.decode(errors="ignore").strip()

                if request == "GET":
                    response = get_latest_result_text()
                else:
                    response = "ERROR unknown command\n"

                conn.sendall(response.encode())

            except socket.timeout:
                continue

            except Exception as e:
                try:
                    conn.sendall(f"ERROR {e}\n".encode())
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
    return render_template_string("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Line Trace Vision Demo</title>
  <style>
    body {
      font-family: sans-serif;
      background: #111;
      color: #eee;
      text-align: center;
    }
    h1 {
      margin-top: 20px;
    }
    img {
      width: 90%;
      max-width: 900px;
      border: 4px solid #555;
      border-radius: 12px;
    }
    .note {
      font-size: 1.2em;
      margin: 16px;
    }
    .small {
      color: #aaa;
      font-size: 0.9em;
      margin-top: 8px;
    }
  </style>
</head>
<body>
  <h1>ETロボコン ライントレース画像認識デモ</h1>
  <div class="note">
    Raspberry Pi Camera Module の画像から黒ラインを検出し、
    旋回方向を推定しています。
  </div>
  <img src="/video">
  <div class="small">
    Web表示はデモ用に軽量化しています。
  </div>
</body>
</html>
""")


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
    vision_thread = threading.Thread(target=vision_loop, daemon=True)
    tcp_thread = threading.Thread(target=tcp_server_loop, daemon=True)

    vision_thread.start()
    tcp_thread.start()

    web_server_loop()


if __name__ == "__main__":
    main()
