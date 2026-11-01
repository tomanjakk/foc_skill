/**
 * @file    kth71xx.h
 * @brief   KTH7111 磁编码器硬件驱动头文件
 *
 * 本模块封装 KTH7111 编码器芯片的所有硬件交互：
 *   - SPI 通信初始化
 *   - 角度原始值读取
 *   - 寄存器读写、解锁/加锁、MTP 写入
 *   - 自动非线性校准（ANLC）
 *
 * 移植说明：
 *   若更换编码器芯片，需替换本文件和 kth71xx.c，
 *   并保证新驱动实现以下两个接口供 encoder.c 调用：
 *     void     Encoder_HW_Init(void);       // 编码器硬件初始化
 *     uint16_t Encoder_HW_ReadRaw(void);    // 读取原始角度值（0 ~ CPR-1）
 */

#ifndef __KTH71XX_H
#define __KTH71XX_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* -----------------------------------------------------------------------
 * 引脚定义（根据实际硬件修改）
 * ----------------------------------------------------------------------- */
#define KTH71_CAL_PORT    GPIOB
#define KTH71_CAL_PIN     GPIO_PINS_5   /* CAL 引脚，保持低电平 */

#define KTH71_CS_PORT     GPIOB
#define KTH71_CS_PIN      GPIO_PINS_6   /* 片选，低有效 */

#define KTH71_SDA_PORT    GPIOB
#define KTH71_SDA_PIN     GPIO_PINS_7   /* SPI2 MOSI 半双工（MUX5） */

#define KTH71_SCK_PORT    GPIOB
#define KTH71_SCK_PIN     GPIO_PINS_8   /* SPI2 SCK（MUX5） */

/* ---- 片选控制宏 ---- */
#define ENC_CS_ENABLE     gpio_bits_reset(KTH71_CS_PORT, KTH71_CS_PIN)
#define ENC_CS_DISABLE    gpio_bits_set(KTH71_CS_PORT, KTH71_CS_PIN)

/* -----------------------------------------------------------------------
 * SPI 命令字节（KTH7111 datasheet）
 * ----------------------------------------------------------------------- */
#define KTH71_READ_ANGLE    0x00u
#define KTH71_READ_REG      0x11u
#define KTH71_WRITE_REG     0x33u

/* -----------------------------------------------------------------------
 * 内部寄存器地址
 * ----------------------------------------------------------------------- */
#define KTH71_REG_CAL_ADDR         0x16u
#define KTH71_ANLC_STATUS_ADDR     0x72u

/* ---- ANLC 状态枚举 ---- */
typedef enum {
    KTH71_ANLC_STATUS_NONE     = 0,
    KTH71_ANLC_STATUS_ONGOING  = 1,
    KTH71_ANLC_STATUS_FAIL     = 2,
    KTH71_ANLC_STATUS_COMPLETE = 3,
} KTH71_ANLC_STATUS_E;

/* -----------------------------------------------------------------------
 * 编码器驱动统一接口（encoder.c 通过这两个函数访问硬件）
 * 更换编码器时，新驱动必须实现这两个函数
 * ----------------------------------------------------------------------- */

/**
 * @brief  编码器硬件初始化（GPIO、SPI 外设等）
 */
void Encoder_HW_Init(void);

/**
 * @brief  读取编码器原始角度值
 * @retval 原始角度计数值，范围 0 ~ CPR-1（KTH7111 为 0~65535）
 */
uint16_t Encoder_HW_ReadRaw(void);

/* -----------------------------------------------------------------------
 * KTH7111 芯片特有功能（非通用接口，仅 KTH71xx 驱动提供）
 * ----------------------------------------------------------------------- */
uint8_t KTH71_ReadAngle(uint16_t *pAngle);
uint8_t KTH71_ReadReg(uint8_t addr, uint8_t *pRegValue);
uint8_t KTH71_ReadReg0x11(uint8_t *pRegValue);
uint8_t KTH71_WriteReg(uint8_t addr, uint8_t data);
void    KTH71_UnlockReg(void);
void    KTH71_LockReg(void);
void    KTH71_WriteRegToMTP(void);
uint8_t KTH71_AutoNLCalibByReg(void);
void    KTH71_BootCheck(void);

#ifdef __cplusplus
}
#endif

#endif /* __KTH71XX_H */
