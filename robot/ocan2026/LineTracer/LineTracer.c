#include "app.h"
#include "LineTracer.h"
#include "LineTracerControl.h"

#include <stddef.h>
#include <stdlib.h>

#include "spike/pup/colorsensor.h"
#include "spike/pup/motor.h"

static pup_motor_t *left_motor;
static pup_motor_t *right_motor;
static pup_device_t *color_sensor;
static float difference=0;
//static float brightness=0;
static int steering=0;

static int threshold(void)
{
    return (WHITE_BRIGHTNESS + BLACK_BRIGHTNESS) / 2;
}

static int clamp_power(int power)
{
    if (power > 100) {
        return 100;
    }
    if (power < -100) {
        return -100;
    }
    return power;
}

/* 学習タスクは指令を置くだけ。実機APIはmain_taskだけが呼ぶ。 */
static volatile bool output_enabled;
static volatile bool output_pending;
static volatile int requested_left;
static volatile int requested_right;

static void drive(int left_power, int right_power)
{
    if (loc_cpu() != E_OK) {
        return;
    }
    if (output_enabled) {
        requested_left = clamp_power(left_power);
        requested_right = clamp_power(right_power);
        output_pending = true;
    }
    (void)unl_cpu();
}

static bool write_power(int left_power, int right_power)
{
    /* ACK待ちを伴うstop/brakeではなく従来のset_power(0)を使用する。 */
    bool left_ok = left_motor != NULL
        && pup_motor_set_power(left_motor, left_power) == PBIO_SUCCESS;
    bool right_ok = right_motor != NULL
        && pup_motor_set_power(right_motor, right_power) == PBIO_SUCCESS;
    return left_ok && right_ok;
}

bool LineTracer_SetRunning(bool running)
{
    if (loc_cpu() != E_OK) {
        return false;
    }
    output_enabled = running;
    requested_left = 0;
    requested_right = 0;
    output_pending = false;
    (void)unl_cpu();
    /* 開始・停止とも必ずゼロ。古い要求を再開時に出力しない。 */
    return write_power(0, 0);
}

bool LineTracer_FlushOutput(void)
{
    int left_power;
    int right_power;
    bool pending;
    if (loc_cpu() != E_OK) {
        return false;
    }
    pending = output_pending && output_enabled;
    left_power = requested_left;
    right_power = requested_right;
    output_pending = false;
    (void)unl_cpu();
    return !pending || write_power(left_power, right_power);
}

bool LineTracer_Configure(pbio_port_id_t left_motor_port,
                          pbio_port_id_t right_motor_port,
                          pbio_port_id_t color_sensor_port)
{
    bool left_ok;
    bool right_ok;
    bool stopped;
    output_enabled = false;
    output_pending = false;
    color_sensor = pup_color_sensor_get_device(color_sensor_port);
    left_motor = pup_motor_get_device(left_motor_port);
    right_motor = pup_motor_get_device(right_motor_port);
    left_ok = left_motor != NULL
        && pup_motor_setup(left_motor, PUP_DIRECTION_COUNTERCLOCKWISE, true) == PBIO_SUCCESS;
    right_ok = right_motor != NULL
        && pup_motor_setup(right_motor, PUP_DIRECTION_CLOCKWISE, true) == PBIO_SUCCESS;
    stopped = write_power(0, 0);
    return left_ok && right_ok && color_sensor != NULL && stopped;
}

int32_t brightness(void)
{
    return pup_color_sensor_reflection(color_sensor);
}

bool black(void)
{
    difference = (float)abs((brightness() - threshold()));
    steering = (int)(difference * STEERING_COEF);
    return brightness() < threshold();
}

bool white(void)
{
    difference = (float)abs((brightness() - threshold()));
    steering = (int)(difference * STEERING_COEF);
    return !black();
}

void stop(void)
{
    drive(0, 0);
}

void forward(void)
{
    drive(BASE_SPEED, BASE_SPEED);
}

void left(void)
{
    drive(BASE_SPEED - steering, BASE_SPEED + steering);
}

void right(void)
{
    drive(BASE_SPEED + steering, BASE_SPEED - steering);
}

/*void smooth_trace(void)
{
    const float difference = (float)(threshold() - brightness());
    const int steering = (int)(difference * STEERING_COEF);

    黒線の左側の境界を走る（左右を交換すると反対側を走る）。 
    drive(BASE_SPEED + steering, BASE_SPEED - steering);
} */
