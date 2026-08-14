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
#define WHITE_BRIGHTNESS 30
#define BLACK_BRIGHTNESS 0
#define BLACK_REFLECTION_THRESHOLD \
    ((WHITE_BRIGHTNESS + BLACK_BRIGHTNESS) / 2)

static volatile bool fg_paused = true;
static pup_motor_t *fg_left_motor = NULL;
static pup_motor_t *fg_right_motor = NULL;
static pup_device_t *fg_color_sensor = NULL;
static bool fg_server_connected = false;
static int fg_applied_left_pwm = 0;
static int fg_applied_right_pwm = 0;

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

static bool color_sensor_is_black(void)
{
    if (fg_color_sensor == NULL) {
        return true;
    }

    return pup_color_sensor_reflection(fg_color_sensor)
        < BLACK_REFLECTION_THRESHOLD;
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
    bool black_stop;

    (void)unused;

    black_stop = color_sensor_is_black();

    if (!fg_server_connected) {
        fg_server_connected = PwmClient_Connect(PWM_SERVER_HOST, PWM_SERVER_PORT);
    }

    if (!fg_server_connected || !PwmClient_Get(
            &left_pwm, &right_pwm, !fg_paused, black_stop,
            fg_applied_left_pwm, fg_applied_right_pwm)) {
        fg_server_connected = false;
        stop_motors();
        ext_tsk();
        return;
    }

    if (fg_paused || black_stop || color_sensor_is_black()) {
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
