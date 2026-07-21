import cv2
import numpy as np


def estimate_steering(image):
    """
    カメラ画像から旋回量を推定する。

    Parameters
    ----------
    image : numpy.ndarray
        OpenCVで読み込んだ画像

    Returns
    -------
    steering : float
        -1.0 〜 +1.0 の旋回量
        負: 左旋回、正: 右旋回、0: 直進

    confidence : float
        0.0 〜 1.0 の信頼度

    debug_info : dict
        描画用の中間情報
    """
    h, w = image.shape[:2]

    # 1. グレースケール化
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. 黒い部分を抽出する
    # 80より暗い画素を黒線候補とする
    threshold_value = 80
    _, black = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY_INV)

    # 3. 見る範囲を決める
    # カーブで黒線が左右に寄るため、左右はやや広めに見る
    x_min = int(w * 0.10)
    x_max = int(w * 0.90)

    # ロボットに近い下側を重視する
    y_min = int(h * 0.45)
    y_max = int(h * 0.90)

    mask = np.zeros_like(black)
    mask[y_min:y_max, x_min:x_max] = 255

    target = cv2.bitwise_and(black, mask)

    # 4. 複数の高さで黒線の中心を求める
    ys = [
        int(h * 0.55),
        int(h * 0.70),
        int(h * 0.85),
    ]

    band_half_height = 6

    centers = []
    valid_ys = []
    counts = []

    for y in ys:
        y1 = max(0, y - band_half_height)
        y2 = min(h, y + band_half_height)

        band = target[y1:y2, :]
        xs = np.where(band > 0)[1]

        if len(xs) > 0:
            centers.append(float(np.mean(xs)))
            valid_ys.append(y)
            counts.append(len(xs))

    # 5. 検出できなければ直進・低信頼度
    if len(centers) == 0:
        debug_info = {
            "gray": gray,
            "black": black,
            "target": target,
            "roi": (x_min, y_min, x_max, y_max),
            "ys": ys,
            "valid_ys": [],
            "centers": [],
            "counts": [],
            "x_line": None,
            "image_center": w / 2,
            "dx": 0.0,
            "threshold_value": threshold_value,
            "steering_scale": w * 0.35,
        }
        return 0.0, 0.0, debug_info

    # 6. 下側ほど重視して、黒線の代表位置を決める
    # 例：検出点が3つなら [1.0, 1.5, 2.0]
    weights = np.linspace(1.0, 2.0, len(centers))
    x_line = float(np.average(centers, weights=weights))

    # 7. 画像中央からのずれを steering にする
    image_center = w / 2
    dx = x_line - image_center

    steering_scale = w * 0.35
    steering = dx / steering_scale
    steering = float(np.clip(steering, -1.0, 1.0))

    confidence = len(centers) / len(ys)

    debug_info = {
        "gray": gray,
        "black": black,
        "target": target,
        "roi": (x_min, y_min, x_max, y_max),
        "ys": ys,
        "valid_ys": valid_ys,
        "centers": centers,
        "counts": counts,
        "weights": weights,
        "x_line": x_line,
        "image_center": image_center,
        "dx": dx,
        "threshold_value": threshold_value,
        "steering_scale": steering_scale,
    }

    return steering, confidence, debug_info


def draw_debug(image, steering, confidence, debug_info):
    """
    推定結果とアルゴリズムの中間情報を画像上に描画する。
    """
    debug = image.copy()
    h, w = debug.shape[:2]

    # -----------------------------
    # 1. ROIを描画
    # -----------------------------
    x_min, y_min, x_max, y_max = debug_info["roi"]

    cv2.rectangle(
        debug,
        (x_min, y_min),
        (x_max, y_max),
        (0, 255, 255),
        2,
    )

    cv2.putText(
        debug,
        "ROI",
        (x_min + 5, y_min - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # -----------------------------
    # 2. 調査している横帯を描画
    # -----------------------------
    ys = debug_info["ys"]
    band_half_height = 6

    for y in ys:
        cv2.line(
            debug,
            (x_min, y),
            (x_max, y),
            (255, 255, 0),
            1,
        )

        cv2.rectangle(
            debug,
            (x_min, max(0, y - band_half_height)),
            (x_max, min(h, y + band_half_height)),
            (255, 255, 0),
            1,
        )

    # -----------------------------
    # 3. 各高さで求めた黒線中心を描画
    # -----------------------------
    valid_ys = debug_info["valid_ys"]
    centers = debug_info["centers"]
    counts = debug_info["counts"]

    for i, (x, y) in enumerate(zip(centers, valid_ys)):
        p = (int(x), int(y))

        cv2.circle(
            debug,
            p,
            8,
            (0, 255, 0),
            -1,
        )

        cv2.putText(
            debug,
            f"c{i}: x={x:.0f}, n={counts[i]}",
            (int(x) + 10, int(y) - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    # -----------------------------
    # 4. 画像中央線を描画
    # -----------------------------
    image_center = debug_info["image_center"]

    cv2.line(
        debug,
        (int(image_center), y_min),
        (int(image_center), y_max),
        (255, 0, 0),
        2,
    )

    cv2.putText(
        debug,
        "image center",
        (int(image_center) + 5, y_min + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 0),
        2,
        cv2.LINE_AA,
    )

    # -----------------------------
    # 5. 推定した黒線代表位置を描画
    # -----------------------------
    x_line = debug_info["x_line"]

    if x_line is not None:
        cv2.line(
            debug,
            (int(x_line), y_min),
            (int(x_line), y_max),
            (0, 0, 255),
            2,
        )

        cv2.putText(
            debug,
            "x_line",
            (int(x_line) + 5, y_max - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        # image_center から x_line までのずれを矢印で表示
        y_arrow = int(h * 0.78)

        cv2.arrowedLine(
            debug,
            (int(image_center), y_arrow),
            (int(x_line), y_arrow),
            (0, 0, 255),
            3,
        )

    # -----------------------------
    # 6. 旋回方向の矢印を描画
    # -----------------------------
    start = (w // 2, h - 30)
    end = (int(w // 2 + steering * 180), h - 120)

    cv2.arrowedLine(
        debug,
        start,
        end,
        (0, 0, 255),
        3,
    )

    # -----------------------------
    # 7. テキスト情報を描画
    # -----------------------------
    dx = debug_info["dx"]
    threshold_value = debug_info["threshold_value"]
    steering_scale = debug_info["steering_scale"]

    lines = [
        f"steering = {steering:+.2f}",
        f"confidence = {confidence:.2f}",
        f"threshold = {threshold_value}",
        f"x_line = {x_line:.1f}" if x_line is not None else "x_line = None",
        f"center = {image_center:.1f}",
        f"dx = x_line - center = {dx:+.1f}",
        f"scale = {steering_scale:.1f}",
    ]

    x_text = 20
    y_text = 30
    line_height = 26

    for i, line in enumerate(lines):
        cv2.putText(
            debug,
            line,
            (x_text, y_text + i * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    # -----------------------------
    # 8. 黒抽出画像を小さく重ねる
    # -----------------------------
    target = debug_info["target"]

    small_w = int(w * 0.28)
    small_h = int(h * 0.28)

    target_small = cv2.resize(target, (small_w, small_h))
    target_small_bgr = cv2.cvtColor(target_small, cv2.COLOR_GRAY2BGR)

    # 右上に貼る
    x0 = w - small_w - 20
    y0 = 20

    debug[y0:y0 + small_h, x0:x0 + small_w] = target_small_bgr

    cv2.rectangle(
        debug,
        (x0, y0),
        (x0 + small_w, y0 + small_h),
        (255, 255, 255),
        2,
    )

    cv2.putText(
        debug,
        "black pixels in ROI",
        (x0, y0 + small_h + 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return debug