#ifndef TEST_COLOR_H
#define TEST_COLOR_H
#include "spikeapi.h"
typedef struct { int port; } pup_device_t;
pup_device_t *pup_color_sensor_get_device(pbio_port_id_t port);
int32_t pup_color_sensor_reflection(pup_device_t *sensor);
#endif
