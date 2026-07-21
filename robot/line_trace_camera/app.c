#include "app.h"
#include <stdio.h>
#include "LineTracer.h"

#include "spike/pup/forcesensor.h"

/* センサーポートの定義 */
static const pbio_port_id_t
  color_sensor_port    = PBIO_PORT_ID_E,
  left_motor_port      = PBIO_PORT_ID_B,
  right_motor_port     = PBIO_PORT_ID_A,
  force_sensor_port    = PBIO_PORT_ID_D;

static void wait_force_sensor_pressed(pup_device_t *force_sensor) {
  while (!pup_force_sensor_touched(force_sensor)) {
    dly_tsk(10 * 1000);
  }
}

static void wait_force_sensor_released(pup_device_t *force_sensor) {
  while (pup_force_sensor_touched(force_sensor)) {
    dly_tsk(10 * 1000);
  }
}

void main_task(intptr_t unused) {
  printf("+---------------------------------+\n");
  printf("|   Press force sensor to start   |\n");
  printf("+---------------------------------+\n");

  pup_device_t *force_sensor = pup_force_sensor_get_device(force_sensor_port);

  /*
   * 初期化は1回だけ
   */
  LineTracer_Configure(left_motor_port, right_motor_port, color_sensor_port);
  LineTracer_ConnectVisionServer();

  /*
   * 周期タスクは1回だけ起動する
   */
  LineTracer_Pause();
  sta_cyc(LINE_TRACER_TASK_CYC);

  while (1) {
    printf("Standby mode. Press force sensor to start.\n");

    wait_force_sensor_pressed(force_sensor);
    wait_force_sensor_released(force_sensor);

    printf("Resume Line Trace!!\n");
    LineTracer_Resume();

    printf("Running. Press force sensor again to pause.\n");

    wait_force_sensor_pressed(force_sensor);
    wait_force_sensor_released(force_sensor);

    printf("Pause Line Trace. Motor off.\n");
    LineTracer_Pause();
  }
}