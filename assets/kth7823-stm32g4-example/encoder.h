#ifndef __ENCODER_H__
#define __ENCODER_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* 编码器SPI固定使用DMA；DMA完成回调自动启动下一帧采样。 */

extern volatile uint16_t g_encoder_angle_raw;
extern volatile uint32_t g_encoder_read_success_count;
extern volatile uint32_t g_encoder_read_fail_count;
extern volatile uint32_t g_encoder_invalid_sample_streak;

HAL_StatusTypeDef KTH7823_Init(void);

uint16_t KTH7823_ReadRawAngle(void);
uint8_t KTH7823_ReadOK(void);
HAL_StatusTypeDef KTH7823_GetLastStatus(void);

#ifdef __cplusplus
}
#endif

#endif
