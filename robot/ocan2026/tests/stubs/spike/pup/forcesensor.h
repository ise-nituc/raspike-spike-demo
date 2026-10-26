#ifndef TEST_FORCE_H
#define TEST_FORCE_H
#include "spike/pup/colorsensor.h"
pup_device_t *pup_force_sensor_get_device(pbio_port_id_t port);
bool pup_force_sensor_touched(pup_device_t *sensor);
#endif
