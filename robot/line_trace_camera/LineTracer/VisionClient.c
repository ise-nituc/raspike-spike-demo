#include "VisionClient.h"

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>

#include <sys/types.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/in.h>

static int fg_sock = -1;

bool VisionClient_Connect(const char *host, int port)
{
    struct sockaddr_in server_addr;

    if (fg_sock >= 0) {
        return true;
    }

    fg_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (fg_sock < 0) {
        printf("VisionClient: socket failed\n");
        return false;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons((uint16_t)port);

    if (inet_pton(AF_INET, host, &server_addr.sin_addr) <= 0) {
        printf("VisionClient: invalid host: %s\n", host);
        close(fg_sock);
        fg_sock = -1;
        return false;
    }

    if (connect(fg_sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        printf("VisionClient: connect failed: %s:%d\n", host, port);
        close(fg_sock);
        fg_sock = -1;
        return false;
    }

    printf("VisionClient: connected to %s:%d\n", host, port);
    return true;
}

void VisionClient_Close(void)
{
    if (fg_sock >= 0) {
        close(fg_sock);
        fg_sock = -1;
    }
}

bool VisionClient_Get(float *steering, float *confidence)
{
    char recv_buf[128];
    int len;
    float s = 0.0f;
    float c = 0.0f;
    int count = 0;
    double timestamp = 0.0;

    if (fg_sock < 0) {
        return false;
    }

    len = send(fg_sock, "GET\n", 4, 0);
    if (len <= 0) {
        printf("VisionClient: send failed\n");
        VisionClient_Close();
        return false;
    }

    memset(recv_buf, 0, sizeof(recv_buf));
    len = recv(fg_sock, recv_buf, sizeof(recv_buf) - 1, 0);

    if (len <= 0) {
        printf("VisionClient: recv failed\n");
        VisionClient_Close();
        return false;
    }

    recv_buf[len] = '\0';

    /*
     * Python側の形式:
     * steering confidence count timestamp
     */
    if (sscanf(recv_buf, "%f %f %d %lf", &s, &c, &count, &timestamp) < 2) {
        printf("VisionClient: parse failed: %s\n", recv_buf);
        return false;
    }

    *steering = s;
    *confidence = c;

    return true;
}
