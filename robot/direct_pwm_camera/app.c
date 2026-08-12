#include "app.h"

#include <stdio.h>

#include "DirectPwmController.h"
#include "spike/pup/forcesensor.h"

static const pbio_port_id_t left_motor_port = PBIO_PORT_ID_B;
static const pbio_port_id_t right_motor_port = PBIO_PORT_ID_A;
static const pbio_port_id_t color_sensor_port = PBIO_PORT_ID_E;
static const pbio_port_id_t force_sensor_port = PBIO_PORT_ID_D;

static void wait_force_sensor_pressed(pup_device_t *force_sensor)
{
    while (!pup_force_sensor_touched(force_sensor)) {
        dly_tsk(10 * 1000);
    }
}

static void wait_force_sensor_released(pup_device_t *force_sensor)
{
    while (pup_force_sensor_touched(force_sensor)) {
        dly_tsk(10 * 1000);
    }
}

void main_task(intptr_t unused)
{
    pup_device_t *force_sensor;

    (void)unused;

    printf("+---------------------------------+\n");
    printf("|   Press force sensor to start   |\n");
    printf("+---------------------------------+\n");

    force_sensor = pup_force_sensor_get_device(force_sensor_port);
    DirectPwmController_Configure(
        left_motor_port, right_motor_port, color_sensor_port);
    DirectPwmController_ConnectServer();

    DirectPwmController_Pause();
    sta_cyc(DIRECT_PWM_TASK_CYC);

    while (1) {
        printf("Standby mode. Press force sensor to start.\n");
        wait_force_sensor_pressed(force_sensor);
        wait_force_sensor_released(force_sensor);

        printf("Resume direct PWM control.\n");
        DirectPwmController_Resume();

        printf("Running. Press force sensor again to pause.\n");
        wait_force_sensor_pressed(force_sensor);
        wait_force_sensor_released(force_sensor);

        printf("Pause direct PWM control. Motor off.\n");
        DirectPwmController_Pause();
    }
}
