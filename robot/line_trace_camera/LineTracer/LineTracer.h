#ifdef __cplusplus
extern "C" {
#endif

/* 下記の項目は各ロボットに合わせて変えること */

/* カラーセンサの輝度設定 */
#define WHITE_BRIGHTNESS  (40)
#define BLACK_BRIGHTNESS  (10) 

/* ステアリング操舵量の係数 */
#define STEERING_COEF     (1.5F) 

/* 走行基準スピード */
#define BASE_SPEED        (70) 

/* ライントレースエッジ切り替え */
#define LEFT_EDGE         (1) 
#define RIGHT_EDGE        (1) 

#include "pbio/port.h"  
#include <stdbool.h>

  extern void LineTracer_Configure(pbio_port_id_t left_motor_port, pbio_port_id_t right_motor_port, pbio_port_id_t color_sensor_port);
  extern void LineTracer_ConnectVisionServer(void);

  void LineTracer_Pause(void);
  void LineTracer_Resume(void);
  bool LineTracer_IsPaused(void);

#ifdef __cplusplus
}
#endif
