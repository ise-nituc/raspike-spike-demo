#ifndef OCAN_ROBOT_CONTROL_H
#define OCAN_ROBOT_CONTROL_H

#include <stdbool.h>
#include "pbio/port.h"

/* 固定コード専用。main_task（学習タスクより高優先度）からだけ呼ぶ。 */
#define BUTTON_POLL_PERIOD_US (10 * 1000)
#define BUTTON_STABLE_SAMPLES 4

bool RobotControl_Init(pbio_port_id_t force_port);
void RobotControl_Poll(void);

#endif
