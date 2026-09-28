#ifdef __cplusplus
extern "C" {
#endif

#include "spikeapi.h"
  
/* タスク優先度 */
#define MAIN_PRIORITY    (TMIN_APP_TPRI + 1) /* メインタスク */
#define TRACER_PRIORITY  (TMIN_APP_TPRI + 2) /* ライントレースタスク */

/* タスク周期の定義 */
#define LINE_TRACER_PERIOD  (100 * 1000) /* ライントレースタスク:100msec周期 */

#define FORCE_SENSOR_PRESSED 10.0 /*フォースセンサ押下判定閾値:10N*/

#ifndef STACK_SIZE
#define STACK_SIZE      (4096)
#endif /* STACK_SIZE */

#ifndef TOPPERS_MACRO_ONLY

extern void main_task(intptr_t exinf);
extern void tracer_task(intptr_t exinf);

#endif /* TOPPERS_MACRO_ONLY */

#ifdef __cplusplus
}
#endif

#define DISPLAY_SIZE 5
static uint8_t DISPLAY_PATTERN[][DISPLAY_SIZE][DISPLAY_SIZE] = 
{{{0,100,0,0,0},
{0,100,100,0,0},
{0,100,100,100,0,},
{0,100,100,0,0},
{0,100,0,0,0}},
{{0,100,0,100,0},
{0,100,0,100,0},
{0,100,0,100,0},
{0,100,0,100,0},
{0,100,0,100,0}}};

#define RUN_STATUS 0
#define POUSE_STATUS 1