#include "app.h"
#include <stdio.h>
#include "LineTracer.h"

#include "RobotControl.h"
#include "LineTracerControl.h"

/* センサーポートの定義 */
static const pbio_port_id_t
  color_sensor_port    = PBIO_PORT_ID_E,
  left_motor_port      = PBIO_PORT_ID_B,
  right_motor_port     = PBIO_PORT_ID_A,
  force_sensor_port    = PBIO_PORT_ID_D;

/*
 * 体験者が編集する場所
 *
 * まず forward(); だけで動かし、次に if 文を追加します。
 * 下の完成例は黒線の左側の境界を走るプログラムです。
 */
void tracer_task(intptr_t unused)
{
  (void)unused;
  if (black()) {
    right();
  } else {
    left();
  }

  ext_tsk();
}

/* 固定の監視・出力タスク。tracer_task()より高優先度で動作する。 */
void main_task(intptr_t unused)
{
  (void)unused;
  if (!LineTracer_Configure(left_motor_port, right_motor_port, color_sensor_port)) {
    (void)LineTracer_SetRunning(false);
    printf("[ocan2026] ERROR: device setup failed; do not run\n");
    ext_tsk();
    return;
  }
  (void)RobotControl_Init(force_sensor_port);
  while (1) {
    if (dly_tsk(BUTTON_POLL_PERIOD_US) != E_OK) {
      (void)LineTracer_SetRunning(false);
      printf("[ocan2026] ERROR: monitor delay failed; end program\n");
      ext_tsk();
      return;
    }
    RobotControl_Poll();
  }
}
