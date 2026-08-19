#include "PwmClient.h"

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#define RESPONSE_BUFFER_SIZE 64

static int fg_sock = -1;

static bool send_all(const char *data, size_t length)
{
    size_t sent = 0;

    while (sent < length) {
        ssize_t result = send(fg_sock, data + sent, length - sent, 0);

        if (result < 0 && errno == EINTR) {
            continue;
        }
        if (result <= 0) {
            return false;
        }
        sent += (size_t)result;
    }

    return true;
}

static bool receive_line(char *buffer, size_t buffer_size)
{
    size_t used = 0;

    while (used + 1 < buffer_size) {
        char received;
        ssize_t result = recv(fg_sock, &received, 1, 0);

        if (result < 0 && errno == EINTR) {
            continue;
        }
        if (result <= 0) {
            return false;
        }
        if (received == '\n') {
            buffer[used] = '\0';
            return true;
        }
        if (received != '\r') {
            buffer[used++] = received;
        }
    }

    buffer[buffer_size - 1] = '\0';
    return false;
}

bool PwmClient_Connect(const char *host, int port)
{
    struct sockaddr_in server_addr;

    if (fg_sock >= 0) {
        return true;
    }

    fg_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (fg_sock < 0) {
        printf("PwmClient: socket failed\n");
        return false;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons((uint16_t)port);

    if (inet_pton(AF_INET, host, &server_addr.sin_addr) <= 0) {
        printf("PwmClient: invalid host: %s\n", host);
        PwmClient_Close();
        return false;
    }

    if (connect(fg_sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        printf("PwmClient: connect failed: %s:%d\n", host, port);
        PwmClient_Close();
        return false;
    }

    printf("PwmClient: connected to %s:%d\n", host, port);
    return true;
}

void PwmClient_Close(void)
{
    if (fg_sock >= 0) {
        close(fg_sock);
        fg_sock = -1;
    }
}

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
    PwmStopConfig *stop_config)
{
    char request[96];
    char response[RESPONSE_BUFFER_SIZE];
    int left;
    int right;
    int mode;
    int reflection;
    int r_min;
    int r_max;
    int g_min;
    int g_max;
    int b_min;
    int b_max;
    char trailing;
    int parsed;

    if (fg_sock < 0 || left_pwm == NULL || right_pwm == NULL
        || stop_config == NULL) {
        return false;
    }

    int request_length = snprintf(
        request,
        sizeof(request),
        "GET %d %d %d %d %d %d %d\n",
        control_enabled ? 1 : 0,
        black_stop ? 1 : 0,
        applied_left_pwm,
        applied_right_pwm,
        sensor_r,
        sensor_g,
        sensor_b);

    if (request_length < 0 || (size_t)request_length >= sizeof(request)
        || !send_all(request, (size_t)request_length)) {
        printf("PwmClient: send failed\n");
        PwmClient_Close();
        return false;
    }

    if (!receive_line(response, sizeof(response))) {
        printf("PwmClient: receive failed\n");
        PwmClient_Close();
        return false;
    }

    parsed = sscanf(
        response,
        "%d:%d:%d:%d:%d:%d:%d:%d:%d:%d%c",
        &left, &right, &mode, &reflection,
        &r_min, &r_max, &g_min, &g_max, &b_min, &b_max, &trailing);

    if (parsed == 10 && mode >= PWM_STOP_DISABLED && mode <= PWM_STOP_RGB) {
        stop_config->mode = (PwmStopMode)mode;
        stop_config->reflection_threshold = reflection;
        stop_config->r_min = r_min;
        stop_config->r_max = r_max;
        stop_config->g_min = g_min;
        stop_config->g_max = g_max;
        stop_config->b_min = b_min;
        stop_config->b_max = b_max;
    } else if (
        sscanf(response, "%d:%d:%d%c", &left, &right, &reflection, &trailing)
        == 3
    ) {
        /* 旧サーバーは反射率閾値だけを返す。 */
        stop_config->mode = PWM_STOP_REFLECTION;
        stop_config->reflection_threshold = reflection;
    } else {
        printf("PwmClient: parse failed: %s\n", response);
        return false;
    }

    *left_pwm = left;
    *right_pwm = right;
    return true;
}
