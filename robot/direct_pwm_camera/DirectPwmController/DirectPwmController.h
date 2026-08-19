#ifndef DIRECT_PWM_CONTROLLER_H
#define DIRECT_PWM_CONTROLLER_H

#include <stdbool.h>

#include "pbio/port.h"

void DirectPwmController_Configure(
    pbio_port_id_t left_motor_port,
    pbio_port_id_t right_motor_port,
    pbio_port_id_t color_sensor_port);
void DirectPwmController_ConnectServer(void);
void DirectPwmController_Pause(void);
void DirectPwmController_Resume(void);
bool DirectPwmController_IsPaused(void);

#endif
