/* Host tests compile the actual application modules; no hardware is accessed. */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include "app.h"
#include "LineTracer.h"
#include "LineTracerControl.h"
#include "RobotControl.h"
#include "spike/pup/motor.h"
#include "spike/pup/forcesensor.h"

_Static_assert(MAIN_PRIORITY < TRACER_PRIORITY, "monitor must preempt learner");
static pup_motor_t left_motor = {PBIO_PORT_ID_B}, right_motor = {PBIO_PORT_ID_A};
static pup_device_t color = {PBIO_PORT_ID_E}, force = {PBIO_PORT_ID_D};
static int left_power, right_power, output_calls, start_calls, stop_calls, terminate_calls, cancel_calls;
static bool pressed, cycle_active, lock_held, force_missing, color_missing, motor_missing;
static ER start_result, stop_result, terminate_result, cancel_result, motor_result, setup_result;
static ER lock_result;
static int monitor_ticks;
static int reflection;
static jmp_buf monitor_exit;

ER loc_cpu(void) {
    if (lock_result != E_OK) return lock_result;
    assert(!lock_held); lock_held = true; return E_OK;
}
ER unl_cpu(void) { assert(lock_held); lock_held = false; return E_OK; }
ER sta_cyc(int id) {
    assert(id == LINE_TRACER_TASK_CYC); ++start_calls;
    if (start_result == E_OK) cycle_active = true;
    return start_result;
}
ER stp_cyc(int id) {
    assert(id == LINE_TRACER_TASK_CYC); ++stop_calls;
    if (stop_result == E_OK) cycle_active = false;
    return stop_result;
}
ER ter_tsk(int id) {
    assert(id == LINE_TRACER_TASK);
    assert(cancel_calls == terminate_calls + 1); /* cancel queued restart before termination */
    ++terminate_calls; return terminate_result;
}
ER_UINT can_act(int id) { assert(id == LINE_TRACER_TASK); ++cancel_calls; return cancel_result; }
ER dly_tsk(unsigned int delay) {
    assert(delay == BUTTON_POLL_PERIOD_US);
    if (++monitor_ticks > 12) longjmp(monitor_exit, 1);
    return E_OK;
}
ER ext_tsk(void) { return E_OK; }
pup_motor_t *pup_motor_get_device(pbio_port_id_t port) {
    if (motor_missing) return NULL;
    assert(port == PBIO_PORT_ID_B || port == PBIO_PORT_ID_A);
    return port == PBIO_PORT_ID_B ? &left_motor : &right_motor;
}
pbio_error_t pup_motor_setup(pup_motor_t *motor, pup_direction_t dir, bool reset) {
    assert(reset);
    assert(dir == (motor == &left_motor ? PUP_DIRECTION_COUNTERCLOCKWISE : PUP_DIRECTION_CLOCKWISE));
    return setup_result;
}
pbio_error_t pup_motor_set_power(pup_motor_t *motor, int power) {
    assert(!lock_held); /* hardware calls must never run inside the mailbox CPU lock */
    assert(power >= -100 && power <= 100);
    ++output_calls;
    if (motor_result != PBIO_SUCCESS) return motor_result;
    if (motor == &left_motor) left_power = power;
    else { assert(motor == &right_motor); right_power = power; }
    return PBIO_SUCCESS;
}
pup_device_t *pup_color_sensor_get_device(pbio_port_id_t port) {
    assert(port == PBIO_PORT_ID_E); return color_missing ? NULL : &color;
}
int32_t pup_color_sensor_reflection(pup_device_t *sensor) { assert(sensor == &color); return reflection; }
pup_device_t *pup_force_sensor_get_device(pbio_port_id_t port) {
    assert(port == PBIO_PORT_ID_D); return force_missing ? NULL : &force;
}
bool pup_force_sensor_touched(pup_device_t *sensor) { assert(sensor == &force); return pressed; }

static void reset(void) {
    left_power = right_power = output_calls = start_calls = stop_calls = 0;
    terminate_calls = cancel_calls = monitor_ticks = reflection = 0;
    pressed = cycle_active = lock_held = force_missing = color_missing = motor_missing = false;
    start_result = stop_result = cancel_result = motor_result = setup_result = lock_result = E_OK;
    terminate_result = E_OBJ; /* dormant learner is a valid stop result */
    assert(LineTracer_Configure(PBIO_PORT_ID_B, PBIO_PORT_ID_A, PBIO_PORT_ID_E));
    assert(RobotControl_Init(PBIO_PORT_ID_D));
    assert(!cycle_active && left_power == 0 && right_power == 0);
}
static void samples(bool down, unsigned int count) {
    pressed = down;
    while (count--) RobotControl_Poll();
}
static void press(void) {
    samples(false, BUTTON_STABLE_SAMPLES);
    samples(true, BUTTON_STABLE_SAMPLES);
}
static void test_button_and_output(void) {
    int previous_calls;
    reset();
    /* Holding at startup is ignored until a stable release followed by a new press. */
    samples(true, 100);
    assert(start_calls == 0);
    samples(false, BUTTON_STABLE_SAMPLES - 1);
    samples(true, 10);
    assert(start_calls == 0);
    samples(false, BUTTON_STABLE_SAMPLES);
    samples(true, BUTTON_STABLE_SAMPLES - 1);
    assert(start_calls == 0);
    samples(true, 1);
    assert(start_calls == 1 && cycle_active);
    previous_calls = output_calls;
    forward();
    assert(output_calls == previous_calls); /* learner only publishes */
    samples(true, 1);
    assert(left_power == BASE_SPEED && right_power == BASE_SPEED);
    samples(true, 100);
    assert(start_calls == 1 && cycle_active);
    /* Both press and release bounce are filtered. */
    samples(false, 1); samples(true, 1); samples(false, 2); samples(true, 2);
    assert(cycle_active);
    terminate_result = E_OK;
    cancel_result = 1; /* queued activation is drained, not replayed */
    forward(); /* pending request at pause must be discarded */
    press();
    assert(!cycle_active && left_power == 0 && right_power == 0);
    assert(terminate_calls == 2 && cancel_calls == 2);
    previous_calls = output_calls;
    forward(); left(); right(); stop();
    assert(output_calls == previous_calls);
    samples(true, 20);
    assert(left_power == 0 && right_power == 0);
    press();
    assert(start_calls == 2 && cycle_active && left_power == 0 && right_power == 0);
    samples(true, 1); /* no replay of the old pending command */
    assert(left_power == 0 && right_power == 0);
    forward(); samples(true, 1);
    assert(left_power == BASE_SPEED && right_power == BASE_SPEED);
    stop(); samples(true, 1);
    assert(left_power == 0 && right_power == 0);
    /* Normal sample task still compiles and publishes through the same mailbox. */
    reflection = 1000;
    tracer_task(0); samples(true, 1);
    assert(left_power == -100 && right_power == 100);
    press();
    assert(!cycle_active && left_power == 0 && right_power == 0);
}
static void test_faults_latch(void) {
    reset(); start_result = E_SYS; press();
    assert(!cycle_active && left_power == 0 && right_power == 0);
    start_result = E_OK; press();
    assert(start_calls == 1 && !cycle_active); /* fault cannot be resumed */

    reset(); press(); forward(); samples(true, 1);
    terminate_result = E_SYS; press();
    assert(left_power == 0 && right_power == 0);
    terminate_result = E_OK; press();
    assert(start_calls == 1);

    reset(); press(); stop_result = E_SYS; press();
    stop_result = E_OK; press(); assert(start_calls == 1);
    reset(); press(); cancel_result = E_SYS; press();
    cancel_result = E_OK; press(); assert(start_calls == 1);

    reset(); press(); motor_result = E_SYS;
    forward(); samples(true, 1); /* flush failure latches fault */
    motor_result = E_OK; samples(true, 1);
    assert(left_power == 0 && right_power == 0);
    press(); assert(start_calls == 1);

    reset(); force_missing = true;
    assert(!RobotControl_Init(PBIO_PORT_ID_D));
    press(); assert(start_calls == 0);
    reset(); color_missing = true;
    assert(!LineTracer_Configure(PBIO_PORT_ID_B, PBIO_PORT_ID_A, PBIO_PORT_ID_E));
    reset(); motor_missing = true;
    assert(!LineTracer_Configure(PBIO_PORT_ID_B, PBIO_PORT_ID_A, PBIO_PORT_ID_E));
    reset(); setup_result = E_SYS;
    assert(!LineTracer_Configure(PBIO_PORT_ID_B, PBIO_PORT_ID_A, PBIO_PORT_ID_E));
    reset(); lock_result = E_SYS;
    assert(!LineTracer_SetRunning(true));
    assert(!LineTracer_FlushOutput());
    forward(); assert(!lock_held);
}
static void test_main_stays_waiting(void) {
    reset(); pressed = true;
    if (setjmp(monitor_exit) == 0) main_task(0);
    assert(monitor_ticks == 13 && !cycle_active && start_calls == 0);
    assert(left_power == 0 && right_power == 0);
}
int main(void) {
    test_button_and_output();
    test_faults_latch();
    test_main_stays_waiting();
    puts("ocan2026 button/output tests: PASS");
    return 0;
}
