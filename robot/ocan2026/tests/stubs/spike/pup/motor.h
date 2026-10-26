#ifndef TEST_MOTOR_H
#define TEST_MOTOR_H
#include "spikeapi.h"
typedef struct { int port; } pup_motor_t;
typedef int pbio_error_t;
typedef enum { PUP_DIRECTION_CLOCKWISE, PUP_DIRECTION_COUNTERCLOCKWISE } pup_direction_t;
#define PBIO_SUCCESS 0
pup_motor_t *pup_motor_get_device(pbio_port_id_t port);
pbio_error_t pup_motor_setup(pup_motor_t *motor, pup_direction_t direction, bool reset);
pbio_error_t pup_motor_set_power(pup_motor_t *motor, int power);
#endif
