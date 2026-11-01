#include "foc_encoder.h"
#include "encoder.h"

#define KTH7823_CS_GPIO_PORT       GPIOA
#define KTH7823_CS_PIN             GPIO_PIN_15
#define KTH7823_SPI_INSTANCE       SPI3
#define KTH7823_SPI_GPIO_PORT      GPIOC
#define KTH7823_SPI_SCK_PIN        GPIO_PIN_10
#define KTH7823_SPI_MISO_PIN       GPIO_PIN_11
#define KTH7823_SPI_MOSI_PIN       GPIO_PIN_12
#define KTH7823_SPI_GPIO_AF        GPIO_AF6_SPI3
#define KTH7823_SPI_BAUDRATE       SPI_BAUDRATEPRESCALER_32
#define KTH7823_SPI_POLL_LIMIT     10000U

static SPI_HandleTypeDef hspi3_encoder;
DMA_HandleTypeDef hdma_spi3_rx;
DMA_HandleTypeDef hdma_spi3_tx;
static volatile uint8_t kth7823_dma_busy;
static uint16_t kth7823_dma_tx_word;
static uint16_t kth7823_dma_rx_word;
static volatile HAL_StatusTypeDef kth7823_last_status = HAL_ERROR;
static HAL_StatusTypeDef KTH7823_TriggerDMA(void);

volatile uint16_t g_encoder_angle_raw;
volatile uint32_t g_encoder_read_success_count;
volatile uint32_t g_encoder_read_fail_count;
volatile uint32_t g_encoder_invalid_sample_streak;

static void KTH7823_CS_Low(void)
{
  HAL_GPIO_WritePin(KTH7823_CS_GPIO_PORT, KTH7823_CS_PIN, GPIO_PIN_RESET);
}

static void KTH7823_CS_High(void)
{
  HAL_GPIO_WritePin(KTH7823_CS_GPIO_PORT, KTH7823_CS_PIN, GPIO_PIN_SET);
}

static void KTH7823_CS_Delay(void)
{
  for (volatile uint32_t i = 0U; i < 64U; ++i) __NOP();
}

static void KTH7823_SPI_WaitIdle(void)
{
  uint32_t timeout = KTH7823_SPI_POLL_LIMIT;

  while ((READ_BIT(hspi3_encoder.Instance->SR, SPI_SR_BSY) != 0U) &&
         (timeout-- > 0U))
  {
  }
}

HAL_StatusTypeDef KTH7823_Init(void)
{
  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  __HAL_RCC_SPI3_CLK_ENABLE();

  gpio.Pin = KTH7823_CS_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_PULLUP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(KTH7823_CS_GPIO_PORT, &gpio);
  KTH7823_CS_High();

  /* SPI3：PC10=SCK，PC11=MISO，PC12=MOSI；PA15 为软件控制片选。 */
  gpio.Pin = KTH7823_SPI_SCK_PIN | KTH7823_SPI_MISO_PIN |
             KTH7823_SPI_MOSI_PIN;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio.Alternate = KTH7823_SPI_GPIO_AF;
  HAL_GPIO_Init(KTH7823_SPI_GPIO_PORT, &gpio);

  hspi3_encoder.Instance = KTH7823_SPI_INSTANCE;
  hspi3_encoder.Init.Mode = SPI_MODE_MASTER;
  hspi3_encoder.Init.Direction = SPI_DIRECTION_2LINES;
  hspi3_encoder.Init.DataSize = SPI_DATASIZE_16BIT;
  hspi3_encoder.Init.CLKPolarity = SPI_POLARITY_HIGH;
  hspi3_encoder.Init.CLKPhase = SPI_PHASE_2EDGE;
  hspi3_encoder.Init.NSS = SPI_NSS_SOFT;
  hspi3_encoder.Init.BaudRatePrescaler = KTH7823_SPI_BAUDRATE;
  hspi3_encoder.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi3_encoder.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi3_encoder.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi3_encoder.Init.CRCPolynomial = 7U;
  hspi3_encoder.Init.CRCLength = SPI_CRC_LENGTH_DATASIZE;
  hspi3_encoder.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;

  kth7823_last_status = HAL_SPI_Init(&hspi3_encoder);
  if (kth7823_last_status != HAL_OK)
    return kth7823_last_status;

  /* SPI3 DMA：DMA1通道2接收，通道3发送。 */
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();

  hdma_spi3_rx.Instance = DMA1_Channel2;
  hdma_spi3_rx.Init.Request = DMA_REQUEST_SPI3_RX;
  hdma_spi3_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;
  hdma_spi3_rx.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_spi3_rx.Init.MemInc = DMA_MINC_DISABLE;
  hdma_spi3_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
  hdma_spi3_rx.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
  hdma_spi3_rx.Init.Mode = DMA_NORMAL;
  hdma_spi3_rx.Init.Priority = DMA_PRIORITY_VERY_HIGH;
  if (HAL_DMA_Init(&hdma_spi3_rx) != HAL_OK)
    return HAL_ERROR;

  hdma_spi3_tx.Instance = DMA1_Channel3;
  hdma_spi3_tx.Init.Request = DMA_REQUEST_SPI3_TX;
  hdma_spi3_tx.Init.Direction = DMA_MEMORY_TO_PERIPH;
  hdma_spi3_tx.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_spi3_tx.Init.MemInc = DMA_MINC_DISABLE;
  hdma_spi3_tx.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
  hdma_spi3_tx.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
  hdma_spi3_tx.Init.Mode = DMA_NORMAL;
  hdma_spi3_tx.Init.Priority = DMA_PRIORITY_VERY_HIGH;
  if (HAL_DMA_Init(&hdma_spi3_tx) != HAL_OK)
    return HAL_ERROR;

  __HAL_LINKDMA(&hspi3_encoder, hdmarx, hdma_spi3_rx);
  __HAL_LINKDMA(&hspi3_encoder, hdmatx, hdma_spi3_tx);

  HAL_NVIC_SetPriority(DMA1_Channel2_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);
  HAL_NVIC_SetPriority(DMA1_Channel3_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel3_IRQn);

  SET_BIT(hspi3_encoder.Instance->CR1, SPI_CR1_SPE);
  /* SPI和DMA初始化完成后立即启动首帧，后续由DMA回调自动续采样。 */
  return KTH7823_TriggerDMA();
}

uint16_t KTH7823_ReadRawAngle(void)
{
  uint16_t angle = g_encoder_angle_raw;

  /* 保持原有FOC节奏：读取最新值后，仅在DMA空闲时启动下一帧。 */
  if (kth7823_dma_busy == 0U)
  {
    (void)KTH7823_TriggerDMA();
  }
  return angle;
}

static HAL_StatusTypeDef KTH7823_TriggerDMA(void)
{
  HAL_StatusTypeDef status;

  if (hspi3_encoder.Instance == 0)
    return HAL_ERROR;
  if (kth7823_dma_busy != 0U)
    return HAL_BUSY;

  /* 新一帧开始前，确保上一帧结束，CS回到高电平并清理残留状态。 */
  KTH7823_SPI_WaitIdle();
  KTH7823_CS_High();
  KTH7823_CS_Delay();
  while (READ_BIT(hspi3_encoder.Instance->SR, SPI_SR_RXNE) != 0U)
    (void)hspi3_encoder.Instance->DR;
  if (READ_BIT(hspi3_encoder.Instance->SR, SPI_SR_OVR) != 0U)
  {
    (void)hspi3_encoder.Instance->DR;
    (void)hspi3_encoder.Instance->SR;
  }

  kth7823_dma_tx_word = 0x0000U;
  kth7823_dma_rx_word = 0U;
  kth7823_dma_busy = 1U;

  /* CS先拉低，再启动DMA，保证KTH7823按完整帧锁存数据。 */
  KTH7823_CS_Low();
  KTH7823_CS_Delay();
  status = HAL_SPI_TransmitReceive_DMA(&hspi3_encoder,
                                       &kth7823_dma_tx_word,
                                       &kth7823_dma_rx_word, 1U);
  if (status != HAL_OK)
  {
    kth7823_dma_busy = 0U;
    KTH7823_CS_High();
    KTH7823_CS_Delay();
    kth7823_last_status = status;
    g_encoder_read_fail_count++;
    g_encoder_invalid_sample_streak++;
  }
  return status;
}


void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi != &hspi3_encoder) return;

  KTH7823_SPI_WaitIdle();
  KTH7823_CS_High();
  KTH7823_CS_Delay();
  g_encoder_angle_raw = kth7823_dma_rx_word;
  kth7823_dma_busy = 0U;
  kth7823_last_status = HAL_OK;
  g_encoder_invalid_sample_streak = 0U;
  g_encoder_read_success_count++;
}

void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi != &hspi3_encoder) return;

  KTH7823_CS_High();
  KTH7823_CS_Delay();
  kth7823_dma_busy = 0U;
  kth7823_last_status = HAL_ERROR;
  g_encoder_read_fail_count++;
  g_encoder_invalid_sample_streak++;
}

uint8_t KTH7823_ReadOK(void)
{
  return (kth7823_last_status == HAL_OK) ? 1U : 0U;
}

HAL_StatusTypeDef KTH7823_GetLastStatus(void)
{
  return kth7823_last_status;
}
