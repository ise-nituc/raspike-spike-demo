#ifndef TEST_SPIKEAPI_H
#define TEST_SPIKEAPI_H
#include <stdint.h>
#include <stdbool.h>
#include "pbio/port.h"
typedef int ER;
typedef int ER_UINT;
#define E_OK 0
#define E_OBJ (-41)
#define E_SYS (-5)
#define TMIN_APP_TPRI 5
#define LINE_TRACER_TASK 2
#define LINE_TRACER_TASK_CYC 1
ER loc_cpu(void);
ER unl_cpu(void);
ER sta_cyc(int id);
ER stp_cyc(int id);
ER ter_tsk(int id);
ER_UINT can_act(int id);
ER dly_tsk(unsigned int delay);
ER ext_tsk(void);
#endif
