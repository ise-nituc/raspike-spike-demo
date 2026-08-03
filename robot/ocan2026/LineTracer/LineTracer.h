#ifndef LINE_TRACER_H
#define LINE_TRACER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stdint.h>
#include "pbio/port.h"

/*
 * 当日の調整項目
 * 白と黒の値は会場のコースで測定し、実測値に置き換えてください。
 */
#define WHITE_BRIGHTNESS  (30)
#define BLACK_BRIGHTNESS  (0)
#define STEERING_COEF     (1.5F)
#define BASE_SPEED        (50)
#define TURN_SPEED        (5)

void LineTracer_Configure(pbio_port_id_t left_motor_port,
                          pbio_port_id_t right_motor_port,
                          pbio_port_id_t color_sensor_port);

/* 中学生が使う命令（昨年度の教材と同じ語彙） */
bool black(void);
bool white(void);
void stop(void);
void forward(void);
void left(void);
void right(void);

/* 発展課題用：明るさに応じて曲がり方を滑らかに変える */
void smooth_trace(void);

/* 実演・調整用 */
int32_t brightness(void);

#ifdef __cplusplus
}
#endif

#endif /* LINE_TRACER_H */
