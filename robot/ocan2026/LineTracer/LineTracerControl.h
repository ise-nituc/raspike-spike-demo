#ifndef OCAN_LINE_TRACER_CONTROL_H
#define OCAN_LINE_TRACER_CONTROL_H

#include <stdbool.h>

/* 実機への出力は高優先度main_taskだけが行う。学習コードから呼ばない。 */
bool LineTracer_SetRunning(bool running);
bool LineTracer_FlushOutput(void);

#endif
