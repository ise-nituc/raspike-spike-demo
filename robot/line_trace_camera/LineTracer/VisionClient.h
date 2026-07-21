#ifndef VISION_CLIENT_H
#define VISION_CLIENT_H

#include <stdbool.h>
#include <stdint.h>

bool VisionClient_Connect(const char *host, int port);
void VisionClient_Close(void);

/*
 * vision serverから最新の操舵量を取得する。
 *
 * steering:
 *   Python側の steering 値。
 *   おおむね -1.0 ～ +1.0。
 *
 * confidence:
 *   ライン検出の確信度。
 *   0.0 ～ 1.0。
 *
 * 戻り値:
 *   true  = 取得成功
 *   false = 取得失敗
 */
bool VisionClient_Get(float *steering, float *confidence);

#endif
