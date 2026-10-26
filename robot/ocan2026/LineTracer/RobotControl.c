#include "app.h"
#include "RobotControl.h"
#include "LineTracerControl.h"
#include "spike/pup/forcesensor.h"

#include <stddef.h>
#include <stdio.h>

static pup_device_t *force_sensor;
static bool candidate_pressed;
static bool stable_pressed;
static unsigned int stable_samples;
static bool armed;
static bool running;
static bool faulted;

/* 起動時は「押下済み」として扱い、安定した解放まで開始を許可しない。 */
static bool new_press(bool pressed)
{
    if (pressed != candidate_pressed) {
        candidate_pressed = pressed;
        stable_samples = 1;
    } else if (stable_samples < BUTTON_STABLE_SAMPLES) {
        ++stable_samples;
    }

    if (stable_samples == BUTTON_STABLE_SAMPLES
            && stable_pressed != candidate_pressed) {
        stable_pressed = candidate_pressed;
        if (!stable_pressed) {
            armed = true;
        } else if (armed) {
            armed = false;
            return true;
        }
    }
    return false;
}

static bool stop_learning(void)
{
    ER cycle_result;
    ER terminate_result;
    ER_UINT cancel_result;
    bool output_ok;

    /* 先にゲートを閉じてゼロ出力。学習タスクの正常終了を待たない。 */
    output_ok = LineTracer_SetRunning(false);
    running = false;
    /* 参照SDK: 未開始の周期もE_OK、休止タスクのcan_actは0、ter_tskはE_OBJ。
     * E_OBJを許容するのはter_tskだけ。ID/未定義/コンテキストエラーは失敗。 */
    cycle_result = stp_cyc(LINE_TRACER_TASK_CYC);
    /* ter_tsk時の予約起動による再活性化を防ぐため、先に予約を消す。 */
    cancel_result = can_act(LINE_TRACER_TASK);
    terminate_result = ter_tsk(LINE_TRACER_TASK);
    return output_ok && cycle_result == E_OK
        && (terminate_result == E_OK || terminate_result == E_OBJ)
        && cancel_result >= 0;
}

static void fail_closed(void)
{
    faulted = true;
    (void)stop_learning();
    printf("[ocan2026] ERROR: stop requested; end program and check hardware/logs\n");
}

bool RobotControl_Init(pbio_port_id_t force_port)
{
    candidate_pressed = true;
    stable_pressed = true;
    stable_samples = 0;
    armed = false;
    running = false;
    faulted = false;
    force_sensor = pup_force_sensor_get_device(force_port);
    if (!stop_learning() || force_sensor == NULL) {
        fail_closed();
        return false;
    }
    printf("[ocan2026] WAITING: release button, then press to run\n");
    return true;
}

void RobotControl_Poll(void)
{
    if (faulted) {
        /* 再起動まで復帰させない。APIエラー時も停止出力を再試行する。 */
        (void)LineTracer_SetRunning(false);
        return;
    }

    if (new_press(pup_force_sensor_touched(force_sensor))) {
        if (running) {
            if (!stop_learning()) {
                fail_closed();
                return;
            }
            printf("[ocan2026] PAUSED: press to run again\n");
        } else {
            if (!LineTracer_SetRunning(true)
                    || sta_cyc(LINE_TRACER_TASK_CYC) != E_OK) {
                fail_closed();
                return;
            }
            running = true;
            printf("[ocan2026] RUNNING\n");
        }
    }
    if (!LineTracer_FlushOutput()) {
        fail_closed();
    }
}
