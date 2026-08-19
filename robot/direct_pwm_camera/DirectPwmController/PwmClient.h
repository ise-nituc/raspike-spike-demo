#ifndef PWM_CLIENT_H
#define PWM_CLIENT_H

#include <stdbool.h>


typedef enum {
    PWM_STOP_DISABLED = 0,
    PWM_STOP_REFLECTION = 1,
    PWM_STOP_RGB = 2
} PwmStopMode;

typedef struct {
    PwmStopMode mode;
    int reflection_threshold;
    int r_min;
    int r_max;
    int g_min;
    int g_max;
    int b_min;
    int b_max;
} PwmStopConfig;
bool PwmClient_Connect(const char *host, int port);
void PwmClient_Close(void);

/* サーバーから ``left:right`` 形式の左右PWM値を取得する。 */
bool PwmClient_Get(
    int *left_pwm,
    int *right_pwm,
    bool control_enabled,
    bool black_stop,
    int applied_left_pwm,
    int applied_right_pwm,
    int sensor_r,
    int sensor_g,
    int sensor_b,
    PwmStopConfig *stop_config);

#endif
