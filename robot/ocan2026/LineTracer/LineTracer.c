#include "app.h"
#include "LineTracer.h"

#include "spike/pup/colorsensor.h"
#include "spike/pup/motor.h"

static pup_motor_t *left_motor;
static pup_motor_t *right_motor;
static pup_device_t *color_sensor;
static float difference=0;
//static float brightness=0;
static int steering=0;

static int threshold(void)
{
    return (WHITE_BRIGHTNESS + BLACK_BRIGHTNESS) / 2;
}

static int clamp_power(int power)
{
    if (power > 100) {
        return 100;
    }
    if (power < -100) {
        return -100;
    }
    return power;
}

static void drive(int left_power, int right_power)
{
    pup_motor_set_power(left_motor, clamp_power(left_power));
    pup_motor_set_power(right_motor, clamp_power(right_power));
}

void LineTracer_Configure(pbio_port_id_t left_motor_port,
                          pbio_port_id_t right_motor_port,
                          pbio_port_id_t color_sensor_port)
{
    color_sensor = pup_color_sensor_get_device(color_sensor_port);
    left_motor = pup_motor_get_device(left_motor_port);
    right_motor = pup_motor_get_device(right_motor_port);

    pup_motor_setup(left_motor, PUP_DIRECTION_COUNTERCLOCKWISE, true);
    pup_motor_setup(right_motor, PUP_DIRECTION_CLOCKWISE, true);
}

int32_t brightness(void)
{
    return pup_color_sensor_reflection(color_sensor);
}

bool black(void)
{
    difference = (float)abs((brightness() - threshold()));
    steering = (int)(difference * STEERING_COEF);
    return brightness() < threshold();
}

bool white(void)
{
    difference = (float)abs((brightness() - threshold()));
    steering = (int)(difference * STEERING_COEF);
    return !black();
}

void stop(void)
{
    drive(0, 0);
}

void forward(void)
{
    drive(BASE_SPEED, BASE_SPEED);
}

void left(void)
{
    drive(BASE_SPEED - steering, BASE_SPEED + steering);
}

void right(void)
{
    drive(BASE_SPEED + steering, BASE_SPEED - steering);
}

/*void smooth_trace(void)
{
    const float difference = (float)(threshold() - brightness());
    const int steering = (int)(difference * STEERING_COEF);

    黒線の左側の境界を走る（左右を交換すると反対側を走る）。 
    drive(BASE_SPEED + steering, BASE_SPEED - steering);
} */