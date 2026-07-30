#ifdef __cplusplus
extern "C" {
#endif

#include "spikeapi.h"

#define MAIN_PRIORITY       (TMIN_APP_TPRI + 1)
#define DIRECT_PWM_PRIORITY (TMIN_APP_TPRI + 2)

/* Python側の制御値を100ミリ秒ごとに取得する。 */
#define DIRECT_PWM_PERIOD (100 * 1000)

#ifndef STACK_SIZE
#define STACK_SIZE (4096)
#endif

#ifndef TOPPERS_MACRO_ONLY

extern void main_task(intptr_t exinf);
extern void direct_pwm_task(intptr_t exinf);

#endif

#ifdef __cplusplus
}
#endif
