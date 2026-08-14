#ifndef PWM_CLIENT_H
#define PWM_CLIENT_H

#include <stdbool.h>

bool PwmClient_Connect(const char *host, int port);
void PwmClient_Close(void);

/* サーバーから ``left:right`` 形式の左右PWM値を取得する。 */
bool PwmClient_Get(
    int *left_pwm,
    int *right_pwm,
    bool control_enabled,
    bool black_stop,
    int applied_left_pwm,
    int applied_right_pwm);

#endif
