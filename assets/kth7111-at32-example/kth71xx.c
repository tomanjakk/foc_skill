/**
 * @file    kth71xx.c
 * @brief   KTH7111 磁编码器硬件驱动
 *
 * 本文件实现 KTH7111 编码器芯片的全部硬件交互：
 *   - SPI2 半双工硬件初始化（Mode3, MSB, ~5.6MHz）
 *   - 角度原始值读取（20kHz ISR 快速路径）
 *   - 寄存器读写、解锁/加锁、MTP 写入
 *   - 自动非线性校准（ANLC）
 *
 * 移植说明：
 *   更换编码器时，仅需替换本文件和 kth71xx.h，
 *   保证实现 Encoder_HW_Init() 和 Encoder_HW_ReadRaw() 即可。
 *   encoder.c 中的 PLL、位置/速度估计逻辑无需修改。
 */

#include "kth71xx.h"
#include "wk_system.h"

/* -----------------------------------------------------------------------
 * CRC8/ITU 查找表
 * poly=0x07, init=0x00, finalXOR=0x55 (KTH7111 datasheet sec6.2)
 * ----------------------------------------------------------------------- */
static const uint8_t CRC8Table[256] =
{
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15,
    0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65,
    0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5,
    0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85,
    0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2,
    0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2,
    0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32,
    0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42,
    0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C,
    0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC,
    0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C,
    0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C,
    0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B,
    0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B,
    0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB,
    0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB,
    0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3
};

/* -----------------------------------------------------------------------
 * 内部静态函数
 * ----------------------------------------------------------------------- */

/**
 * @brief  CRC8 校验
 * @param  pbuf    数据缓冲区
 * @param  buflen  总长度（含 CRC 字节）
 * @retval 1=通过, 0=失败
 */
static uint8_t KTH71_IsCRCOK(uint8_t *pbuf, uint8_t buflen)
{
    uint8_t crc = 0x00;
    uint8_t i;
    for (i = 0; i < (uint8_t)(buflen - 1u); i++)
    {
        crc = CRC8Table[crc ^ pbuf[i]];
    }
    crc ^= 0x55u;
    return (crc == pbuf[buflen - 1u]) ? 1u : 0u;
}

/**
 * @brief  SPI2 半双工收发（硬件 SPI，适合 ISR 高速调用）
 * @param  pTxData  发送缓冲区
 * @param  pRxData  接收缓冲区（可为 NULL）
 * @param  txLen    发送字节数
 * @param  rxLen    接收字节数
 */
static void KTH71_SPI_TransmitReceive(uint8_t *pTxData, uint8_t *pRxData, uint8_t txLen, uint8_t rxLen)
{
    uint8_t i;
    volatile uint8_t flush_dummy;

    /* --- TX 阶段 --- */
    spi_enable(SPI2, FALSE);
    SPI2->ctrl1_bit.slbtd = 1;   /* 发送方向 */
    ENC_CS_ENABLE;
    spi_enable(SPI2, TRUE);

    for (i = 0; i < txLen; i++)
    {
        while (spi_i2s_flag_get(SPI2, SPI_I2S_TDBE_FLAG) == RESET);
        spi_i2s_data_transmit(SPI2, pTxData[i]);
    }
    /* 等待移位寄存器清空（最后一位发送完毕） */
    while (spi_i2s_flag_get(SPI2, SPI_I2S_BF_FLAG) != RESET);
    spi_enable(SPI2, FALSE);

    /* 清空残留 RX 数据 */
    while (spi_i2s_flag_get(SPI2, SPI_I2S_RDBF_FLAG) != RESET)
    {
        flush_dummy = (uint8_t)spi_i2s_data_receive(SPI2);
    }
    (void)flush_dummy;

    /* --- RX 阶段 --- */
    if ((rxLen > 0u) && (pRxData != NULL))
    {
        /* Turnaround：芯片需要时间接管总线 */
        wk_delay_us(2);

        SPI2->ctrl1_bit.slbtd = 0;  /* 接收方向 */
        spi_enable(SPI2, TRUE);     /* 主机开始产生时钟 */

        for (i = 0; i < rxLen; i++)
        {
            /* 读最后一个字节前关闭 SPI 以停止多余时钟 */
            if (i == (uint8_t)(rxLen - 1u))
            {
                spi_enable(SPI2, FALSE);
            }
            while (spi_i2s_flag_get(SPI2, SPI_I2S_RDBF_FLAG) == RESET);
            pRxData[i] = (uint8_t)spi_i2s_data_receive(SPI2);
        }

        /* 恢复发送方向 */
        SPI2->ctrl1_bit.slbtd = 1;
    }

    /* CS 拉高：结束会话。芯片要求 >150ns 间隔 */
    ENC_CS_DISABLE;
    spi_enable(SPI2, TRUE);
}

/* -----------------------------------------------------------------------
 * 编码器驱动统一接口实现
 * 更换编码器时，替换以下两个函数的实现即可
 * ----------------------------------------------------------------------- */

/**
 * @brief  KTH7111 硬件初始化
 *         配置 GPIO 引脚 + SPI2 半双工 Mode3
 */
void Encoder_HW_Init(void)
{
    gpio_init_type  gpio_s;
    spi_init_type   spi_s;

    crm_periph_clock_enable(CRM_GPIOB_PERIPH_CLOCK, TRUE);
    crm_periph_clock_enable(CRM_SPI2_PERIPH_CLOCK,  TRUE);

    gpio_default_para_init(&gpio_s);
    gpio_s.gpio_drive_strength = GPIO_DRIVE_STRENGTH_MODERATE;
    gpio_s.gpio_out_type       = GPIO_OUTPUT_PUSH_PULL;

    /* CAL: 输出，保持低电平 */
    gpio_s.gpio_mode = GPIO_MODE_OUTPUT;
    gpio_s.gpio_pull = GPIO_PULL_DOWN;
    gpio_s.gpio_pins = KTH71_CAL_PIN;
    gpio_init(KTH71_CAL_PORT, &gpio_s);
    gpio_bits_reset(KTH71_CAL_PORT, KTH71_CAL_PIN);

    /* CS: 输出，初始高电平（未选中） */
    gpio_s.gpio_pull = GPIO_PULL_UP;
    gpio_s.gpio_pins = KTH71_CS_PIN;
    gpio_init(KTH71_CS_PORT, &gpio_s);
    ENC_CS_DISABLE;

    /* SCK: MUX5，上拉（Mode3 空闲高） */
    gpio_s.gpio_mode = GPIO_MODE_MUX;
    gpio_s.gpio_pull = GPIO_PULL_UP;
    gpio_s.gpio_pins = KTH71_SCK_PIN;
    gpio_init(KTH71_SCK_PORT, &gpio_s);
    gpio_pin_mux_config(KTH71_SCK_PORT, GPIO_PINS_SOURCE8, GPIO_MUX_5);

    /* SDA: MUX5，上拉（芯片端为开漏） */
    gpio_s.gpio_pull = GPIO_PULL_UP;
    gpio_s.gpio_pins = KTH71_SDA_PIN;
    gpio_init(KTH71_SDA_PORT, &gpio_s);
    gpio_pin_mux_config(KTH71_SDA_PORT, GPIO_PINS_SOURCE7, GPIO_MUX_5);

    /* SPI2: 半双工发送, Mode3, 8-bit, MSB, 软件 CS, ~5.6MHz */
    spi_default_para_init(&spi_s);
    spi_s.transmission_mode      = SPI_TRANSMIT_HALF_DUPLEX_TX;
    spi_s.master_slave_mode      = SPI_MODE_MASTER;
    spi_s.mclk_freq_division     = SPI_MCLK_DIV_32;
    spi_s.first_bit_transmission = SPI_FIRST_BIT_MSB;
    spi_s.frame_bit_num          = SPI_FRAME_8BIT;
    spi_s.clock_polarity         = SPI_CLOCK_POLARITY_HIGH;   /* CPOL=1 */
    spi_s.clock_phase            = SPI_CLOCK_PHASE_2EDGE;      /* CPHA=1 */
    spi_s.cs_mode_selection      = SPI_CS_SOFTWARE_MODE;
    spi_init(SPI2, &spi_s);
    spi_enable(SPI2, TRUE);
}

/**
 * @brief  读取 KTH7111 原始角度值
 * @note   此函数在 20kHz ISR 中被调用，需尽量快速
 * @retval 原始机械角度，范围 0~65535
 */
uint16_t Encoder_HW_ReadRaw(void)
{
    uint8_t  spi_tx_buf = KTH71_READ_ANGLE;
    uint8_t  spi_rx_buf[3];

    KTH71_SPI_TransmitReceive(&spi_tx_buf, spi_rx_buf, 1, 3);
    /* CRC 校验（可选：若追求极致速度可省略） */
    /* KTH71_IsCRCOK(spi_rx_buf, 3); */

    return (uint16_t)(((uint16_t)spi_rx_buf[0] << 8) | spi_rx_buf[1]);
}

/* -----------------------------------------------------------------------
 * KTH7111 芯片特有功能（寄存器操作、校准等）
 * 以下函数仅在初始化/校准时调用，不在 ISR 快速路径中使用
 * ----------------------------------------------------------------------- */

/**
 * @brief  读取角度值（带 CRC 校验结果）
 * @param  pAngle  角度值指针
 * @retval 1=CRC 通过, 0=CRC 失败
 */
uint8_t KTH71_ReadAngle(uint16_t *pAngle)
{
    uint8_t crc_flag;
    uint8_t spi_tx_buf = KTH71_READ_ANGLE;
    uint8_t spi_rx_buf[3];

    KTH71_SPI_TransmitReceive(&spi_tx_buf, spi_rx_buf, 1, 3);
    crc_flag = KTH71_IsCRCOK(spi_rx_buf, 3);
    *pAngle = (uint16_t)(((uint16_t)spi_rx_buf[0] << 8) | spi_rx_buf[1]);
    return crc_flag;
}

/**
 * @brief  读取指定地址的寄存器
 * @param  addr       寄存器地址
 * @param  pRegValue  寄存器值指针
 * @retval 1=CRC 通过, 0=CRC 失败
 */
uint8_t KTH71_ReadReg(uint8_t addr, uint8_t *pRegValue)
{
    uint8_t crc_flag;
    uint8_t spi_tx_buf[2];
    uint8_t spi_rx_buf[2];

    spi_tx_buf[0] = KTH71_READ_REG;
    spi_tx_buf[1] = addr;

    KTH71_SPI_TransmitReceive(spi_tx_buf, spi_rx_buf, 2, 2);
    crc_flag   = KTH71_IsCRCOK(spi_rx_buf, 2);
    *pRegValue = spi_rx_buf[0];
    return crc_flag;
}

/**
 * @brief  读取寄存器 0x11（GAINTRIM）
 * @param  pRegValue  寄存器值指针
 * @retval 1=CRC 通过, 0=CRC 失败
 */
uint8_t KTH71_ReadReg0x11(uint8_t *pRegValue)
{
    return KTH71_ReadReg(0x11u, pRegValue);
}

/**
 * @brief  写入指定地址的寄存器
 * @param  addr  寄存器地址
 * @param  data  写入值
 * @retval 芯片回读的寄存器值
 */
uint8_t KTH71_WriteReg(uint8_t addr, uint8_t data)
{
    uint8_t spi_tx_buf[3];
    uint8_t spi_rx_buf = 0;

    spi_tx_buf[0] = KTH71_WRITE_REG;
    spi_tx_buf[1] = addr;
    spi_tx_buf[2] = data;

    KTH71_SPI_TransmitReceive(spi_tx_buf, &spi_rx_buf, 3, 1);
    return spi_rx_buf;
}

/**
 * @brief  解锁寄存器（写入前必须调用）
 */
void KTH71_UnlockReg(void)
{
    uint8_t buf[4] = {0x20, 0x24, 0x01, 0x01};
    KTH71_SPI_TransmitReceive(buf, NULL, 4, 0);
}

/**
 * @brief  锁定寄存器（写入后调用，防止误修改）
 */
void KTH71_LockReg(void)
{
    uint8_t buf[4] = {0x20, 0x24, 0x12, 0x31};
    KTH71_SPI_TransmitReceive(buf, NULL, 4, 0);
}

/**
 * @brief  将寄存器值写入 MTP（掉电保存）
 * @note   写入后需等待约 400ms
 */
void KTH71_WriteRegToMTP(void)
{
    uint8_t buf[3] = {0x22, 0x55, 0xAA};
    KTH71_SPI_TransmitReceive(buf, NULL, 3, 0);
    wk_delay_ms(400);
}

/**
 * @brief  设置 REG_CAL 位（启动/停止 ANLC）
 * @param  state  1=启动, 0=停止
 * @retval 1=成功, 0=失败
 */
static uint8_t KTH71_SetRegCalState(uint8_t state)
{
    uint8_t ret, reg_data = 0;
    if ((state != 0u) && (state != 1u)) return 0;

    ret = KTH71_ReadReg(KTH71_REG_CAL_ADDR, &reg_data);
    if (ret == 0) return 0;

    KTH71_UnlockReg();
    reg_data = (state == 0u) ? (reg_data & 0xEFu) : (reg_data | 0x10u);
    ret = (reg_data == KTH71_WriteReg(KTH71_REG_CAL_ADDR, reg_data)) ? 1u : 0u;
    wk_delay_ms(10);
    KTH71_LockReg();
    return ret;
}

/**
 * @brief  自动非线性校准（ANLC）
 * @note   阻塞函数，最长等待约 60 秒
 * @retval 1=校准成功, 0=校准失败
 */
uint8_t KTH71_AutoNLCalibByReg(void)
{
    uint8_t  ret = 0, reg_data = 0, saving_flag = 0, status_bit = 0;
    uint16_t cnt;

    if (1u != KTH71_SetRegCalState(1)) return 0;

    for (cnt = 0; cnt < 600u; cnt++)
    {
        wk_delay_ms(100);
        ret = KTH71_ReadReg(KTH71_ANLC_STATUS_ADDR, &reg_data);
        if (ret == 0) break;
        status_bit = (reg_data & 0x30u) >> 4;

        if (saving_flag == 0)
        {
            ret = 0;
            if (status_bit != KTH71_ANLC_STATUS_ONGOING)
            {
                saving_flag = 1;
                wk_delay_ms(1000);
            }
        }
        else
        {
            if (status_bit == KTH71_ANLC_STATUS_COMPLETE)
            {
                ret = 1;
                break;
            }
            else if ((status_bit == KTH71_ANLC_STATUS_FAIL) ||
                     (status_bit == KTH71_ANLC_STATUS_NONE))
            {
                ret = 0;
                break;
            }
            else
            {
                ret = 0;
            }
        }
    }

    KTH71_SetRegCalState(0);
    return ret;
}

/* -----------------------------------------------------------------------
 * 上电一次性检查：确保 reg0x11 为目标值 + 编码器故障校验
 * ----------------------------------------------------------------------- */

/* KTH71xx reg0x11 目标值，修改此宏即可改变判断/写入的值 */
#define KTH71_REG11_TARGET  0x00u

/**
 * @brief  检查 reg0x11 是否为 KTH71_REG11_TARGET，不是则写入
 *         先尝试普通写入，失败则执行完整 MTP 烧录流程
 * @note   调用前需确保 FOC PWM 已关闭，避免 SPI 总线冲突
 */
static void KTH71_EnsureReg11(void)
{
    uint8_t reg11_value = 0xFFu;
    uint8_t read_ok = 0u;

    /* 读取 0x11 */
    read_ok = KTH71_ReadReg(0x11, &reg11_value);

    if (read_ok && reg11_value == KTH71_REG11_TARGET)
    {
        /* 已经是目标值，无需操作 */
        return;
    }

    /* 不是目标值，先普通写入 */
    KTH71_WriteReg(0x11, KTH71_REG11_TARGET);

    /* 回读验证 */
    reg11_value = 0xFFu;
    read_ok = KTH71_ReadReg(0x11, &reg11_value);
    if (read_ok && reg11_value == KTH71_REG11_TARGET)
    {
        return;  /* 普通写入成功 */
    }

    /* 普通写入失败，执行完整烧录流程 */
    wk_delay_ms(50);
    KTH71_UnlockReg();
    KTH71_WriteReg(0x11, KTH71_REG11_TARGET);
    KTH71_WriteRegToMTP();  /* 烧录 */
    KTH71_LockReg();
    wk_delay_ms(50);
}

/**
 * @brief  上电一次性编码器检查
 *         确保 reg0x11 为目标值，并通知保护模块校验结果
 * @note   仅在 main() 主循环中调用一次，内部有 static 标志防止重复执行
 *         调用前后自动 disable/enable FOC PWM
 */
void KTH71_BootCheck(void)
{
    static uint8_t reg11_check_done = 0u;
    if (reg11_check_done != 0u)
        return;

    uint8_t reg11_val = 0xFFu;
    uint8_t read_ok;

    wk_foc_pwm_disable();
    KTH71_EnsureReg11();
    wk_foc_pwm_enable();

    /* 回读 reg0x11 做最终校验，结果送保护模块 */
    read_ok = KTH71_ReadReg(0x11, &reg11_val);

    /* Protect_EncoderCheck 在 foc_protect.c 中实现 */
    extern void Protect_EncoderCheck(uint8_t reg11_ok);
    Protect_EncoderCheck((read_ok && reg11_val == KTH71_REG11_TARGET) ? 1u : 0u);

    reg11_check_done = 1u;
}
