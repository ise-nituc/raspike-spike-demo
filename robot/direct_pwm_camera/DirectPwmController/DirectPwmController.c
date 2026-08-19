#include "app.h"
#include "DirectPwmController.h"
#include "PwmClient.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "spike/pup/motor.h"
#include "spike/pup/colorsensor.h"

#define PWM_SERVER_HOST "127.0.0.1"
#define PWM_SERVER_PORT 65432
#define MOTOR_POWER_MIN (-100)
#define MOTOR_POWER_MAX 100
#define SENSOR_RGB_MAX 1023

static volatile bool fg_paused = true;
static pup_motor_t *fg_left_motor = NULL;
static pup_motor_t *fg_right_motor = NULL;
static pup_device_t *fg_color_sensor = NULL;
static bool fg_server_connected = false;
static int fg_applied_left_pwm = 0;
static int fg_applied_right_pwm = 0;
static PwmStopConfig fg_stop_config = {
    PWM_STOP_DISABLED, 0,
    0, SENSOR_RGB_MAX, 0, SENSOR_RGB_MAX, 0, SENSOR_RGB_MAX
};

static int clamp_motor_power(int power)
{
    if (power < MOTOR_POWER_MIN) {
        return MOTOR_POWER_MIN;
    }
    if (power > MOTOR_POWER_MAX) {
        return MOTOR_POWER_MAX;
    }
    return power;
}

static void stop_motors(void)
{
    fg_applied_left_pwm = 0;
    fg_applied_right_pwm = 0;
    if (fg_left_motor != NULL) {
        pup_motor_stop(fg_left_motor);
    }
    if (fg_right_motor != NULL) {
        pup_motor_stop(fg_right_motor);
    }
}

static bool color_sensor_should_stop(int reflection, pup_color_rgb_t rgb)
{
    if (fg_stop_config.mode == PWM_STOP_DISABLED) {
        return false;
    }
    if (fg_color_sensor == NULL) {
        return true;
    }
    if (fg_stop_config.mode == PWM_STOP_REFLECTION) {
        return reflection < fg_stop_config.reflection_threshold;
    }
    if (fg_stop_config.mode == PWM_STOP_RGB) {
        return rgb.r >= fg_stop_config.r_min
            && rgb.r <= fg_stop_config.r_max
            && rgb.g >= fg_stop_config.g_min
            && rgb.g <= fg_stop_config.g_max
            && rgb.b >= fg_stop_config.b_min
            && rgb.b <= fg_stop_config.b_max;
    }
    return true;
}

void DirectPwmController_Configure(
    pbio_port_id_t left_motor_port,
    pbio_port_id_t right_motor_port,
    pbio_port_id_t color_sensor_port)
{
    fg_color_sensor = pup_color_sensor_get_device(color_sensor_port);
    fg_left_motor = pup_motor_get_device(left_motor_port);
    fg_right_motor = pup_motor_get_device(right_motor_port);

    pup_motor_setup(fg_left_motor, PUP_DIRECTION_COUNTERCLOCKWISE, true);
    pup_motor_setup(fg_right_motor, PUP_DIRECTION_CLOCKWISE, true);
}

void DirectPwmController_ConnectServer(void)
{
    fg_server_connected = PwmClient_Connect(PWM_SERVER_HOST, PWM_SERVER_PORT);

    if (!fg_server_connected) {
        printf("DirectPwmController: PWM server connection failed\n");
    }
}

void direct_pwm_task(intptr_t unused)
{
    int left_pwm = 0;
    int right_pwm = 0;
    int reflection = 0;
    pup_color_rgb_t rgb = {0, 0, 0};
    bool emergency_stop;

    (void)unused;

    if (fg_color_sensor != NULL) {
        reflection = pup_color_sensor_reflection(fg_color_sensor);
        rgb = pup_color_sensor_rgb(fg_color_sensor);
    }
    emergency_stop = color_sensor_should_stop(reflection, rgb);

    if (!fg_server_connected) {
        fg_server_connected = PwmClient_Connect(PWM_SERVER_HOST, PWM_SERVER_PORT);
    }

    if (!fg_server_connected || !PwmClient_Get(
            &left_pwm, &right_pwm, !fg_paused, emergency_stop,
            fg_applied_left_pwm, fg_applied_right_pwm,
            rgb.r, rgb.g, rgb.b, &fg_stop_config)) {
        fg_server_connected = false;
        stop_motors();
        ext_tsk();
        return;
    }

    /* 受信した最新設定でもう一度判定する。 */
    emergency_stop = color_sensor_should_stop(reflection, rgb);
    if (fg_paused || emergency_stop) {
        stop_motors();
        ext_tsk();
        return;
    }

    left_pwm = clamp_motor_power(left_pwm);
    right_pwm = clamp_motor_power(right_pwm);
    pup_motor_set_power(fg_left_motor, left_pwm);
    pup_motor_set_power(fg_right_motor, right_pwm);
    fg_applied_left_pwm = left_pwm;
    fg_applied_right_pwm = right_pwm;

    ext_tsk();
}

void DirectPwmController_Pause(void)
{
    fg_paused = true;
    stop_motors();
}

void DirectPwmController_Resume(void)
{
    fg_paused = false;
}

bool DirectPwmController_IsPaused(void)
{
    return fg_paused;
}
