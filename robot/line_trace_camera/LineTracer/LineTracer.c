#include "app.h"
#include "LineTracer.h"
#include "VisionClient.h"

#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>

#include "spike/pup/motor.h"
#include "spike/pup/colorsensor.h"


/*
 * pauseフラグ。
 * main_task と tracer_task の両方から参照されるので volatile にしておく。
 */
static volatile bool fg_paused = true;


/* 関数プロトタイプ宣言 */
static int16_t steering_amount_calculation(void);
static void motor_drive_control(int16_t steering_amount);


/*
 * このファイル内で保持するデバイスハンドル。
 * fg_ は file global 程度の意味として使う。
 */
static pup_motor_t *fg_left_motor = NULL;
static pup_motor_t *fg_right_motor = NULL;
static pup_device_t *fg_color_sensor = NULL;

static bool fg_vision_connected = false;


/*
 * Python側 steering は -1.0 ～ +1.0 程度。
 * これをモータ制御用の操舵量に変換する係数。
 * 大きすぎると蛇行しやすいので、最初は控えめにする。
 */
#define VISION_STEERING_GAIN  26.0f


/*
 * confidence が低すぎるとライン未検出の可能性が高い。
 */
#define VISION_CONFIDENCE_MIN 0.05f


void LineTracer_Configure(
    pbio_port_id_t left_motor_port,
    pbio_port_id_t right_motor_port,
    pbio_port_id_t color_sensor_port)
{
    /*
     * センサ・モータの取得はここで1回だけ行う。
     * PauseやResumeでは pup_motor_get_device() を呼ばない。
     */
    fg_color_sensor = pup_color_sensor_get_device(color_sensor_port);

    fg_left_motor = pup_motor_get_device(left_motor_port);
    fg_right_motor = pup_motor_get_device(right_motor_port);

    pup_motor_setup(fg_left_motor, PUP_DIRECTION_COUNTERCLOCKWISE, true);
    pup_motor_setup(fg_right_motor, PUP_DIRECTION_CLOCKWISE, true);
}


void LineTracer_ConnectVisionServer(void)
{
    /*
     * Python vision server は同じRaspberry Pi上で動かすため 127.0.0.1。
     */
    fg_vision_connected = VisionClient_Connect("127.0.0.1", 65432);

    if (!fg_vision_connected) {
        printf("LineTracer: vision server connection failed\n");
    }
}


/* ライントレースタスク 100msec周期 */
void tracer_task(intptr_t unused)
{
    int16_t steering_amount;

    /*
     * pause中は何もしない。
     * ただし、タスクとして起動されているので ext_tsk() で終了する。
     */
    if (fg_paused) {
        ext_tsk();
    }

    steering_amount = steering_amount_calculation();

    /*
     * 計算中に pause が入った場合に備えて、モータ駆動直前にも確認する。
     */
    if (fg_paused) {
        ext_tsk();
    }

    motor_drive_control(steering_amount);

    ext_tsk();
}


/* ステアリング操舵量の計算 */
static int16_t steering_amount_calculation(void)
{
    float steering = 0.0f;
    float confidence = 0.0f;
    int16_t steering_amount = 0;

    if (!fg_vision_connected) {
        fg_vision_connected = VisionClient_Connect("127.0.0.1", 65432);
    }

    if (fg_vision_connected) {
        if (VisionClient_Get(&steering, &confidence)) {

            if (confidence < VISION_CONFIDENCE_MIN) {
                /*
                 * ラインを見失った場合。
                 * まずは直進。必要なら停止に変える。
                 */
                steering_amount = 0;
            } else {
                /*
                 * Python側:
                 *   steering < 0 : ラインが左側
                 *   steering > 0 : ラインが右側
                 *
                 * ロボット側で左右が逆なら、ここに - を付ける。
                 */
                steering_amount = (int16_t)(steering * VISION_STEERING_GAIN);
            }

            return steering_amount;
        } else {
            /*
             * 通信失敗時は次回再接続する。
             */
            fg_vision_connected = false;
            return 0;
        }
    }

    /*
     * vision serverに接続できない場合。
     * 安全側で直進または停止。
     */
    return 0;
}


/* 走行モータ制御 */
static void motor_drive_control(int16_t steering_amount)
{
    int left_motor_power;
    int right_motor_power;

    if (fg_left_motor == NULL || fg_right_motor == NULL) {
        return;
    }

    /*
     * 既存コードと同じ計算式。
     * LEFT_EDGE / RIGHT_EDGE の考え方は維持。
     */
    left_motor_power =
        (int)(BASE_SPEED + (steering_amount * LEFT_EDGE));

    right_motor_power =
        (int)(BASE_SPEED - (steering_amount * LEFT_EDGE));

    pup_motor_set_power(fg_left_motor, left_motor_power);
    pup_motor_set_power(fg_right_motor, right_motor_power);
}


/* ライントレース一時停止 */
void LineTracer_Pause(void)
{
    fg_paused = true;

    /*
     * モータ停止。
     * ここでは pup_motor_get_device() を呼ばない。
     * Configure時に取得済みの fg_left_motor / fg_right_motor を使う。
     */
    if (fg_left_motor != NULL) {
        pup_motor_stop(fg_left_motor);
    }

    if (fg_right_motor != NULL) {
        pup_motor_stop(fg_right_motor);
    }
}


/* ライントレース再開 */
void LineTracer_Resume(void)
{
    fg_paused = false;
}


/* pause状態の確認 */
bool LineTracer_IsPaused(void)
{
    return fg_paused;
}