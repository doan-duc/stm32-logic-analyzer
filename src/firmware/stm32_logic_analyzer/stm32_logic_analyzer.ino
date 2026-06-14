/*
 * STM32F103C6 DMA Logic Analyzer - UART Version
 * NOW WITH SLOW SAMPLE RATES (100Hz - 6MHz)
 * Hardware UART on PA9(TX)/PA10(RX)
 */

// Use hardware UART1 instead of USB Serial
HardwareSerial AnalyzerSerial(PA10, PA9); // RX, TX
#undef Serial
#define Serial AnalyzerSerial
#undef LED_BUILTIN
#define LED_BUILTIN PC13
#define BUFFER_SIZE 2048
#define STREAM_CHUNK_SIZE (BUFFER_SIZE / 2)
#define BAUD_RATE 1000000
#define MAX_STREAM_RATE_HZ 50000
#define TRIGGER_PIN_MASK (1U << 0)
#define TRIGGER_TIMEOUT_US 2000000UL

// Sample buffer
uint8_t samples[BUFFER_SIZE];
volatile bool capturing = false;
volatile bool captureComplete = false;
volatile bool streaming = false;
volatile uint8_t streamReadyMask = 0;
volatile uint32_t streamSequence = 0;
volatile uint32_t streamOverruns = 0;
bool triggerEnabled = false;

// Sampling parameters
uint32_t sampleCount = BUFFER_SIZE;
uint32_t sampleRateHz = 100000; // Default: 100kHz (20ms window)

// HAL handles
TIM_HandleTypeDef htim2;
DMA_HandleTypeDef hdma_tim2_up;

// Timeout for stuck captures
uint32_t captureStartTime = 0;
#define CAPTURE_TIMEOUT_MS 30000 // 30 seconds (for slow rates)

bool waitForPA0FallingEdge();
bool configureDMA(uint32_t mode);
bool startDMA(uint32_t count);
void startStreaming();
void stopStreaming();
void sendStreamChunk(uint8_t half);
void DMA_XferHalfCallback(DMA_HandleTypeDef *hdma);
uint16_t streamCRC16(const uint8_t *data, uint32_t length);

void setup() {
  Serial.begin(BAUD_RATE);
  delay(100);

  // Configure GPIOB 0-7 as inputs
  pinMode(PA0, INPUT_PULLDOWN);
  pinMode(PA1, INPUT_PULLDOWN);
  pinMode(PA2, INPUT_PULLDOWN);
  pinMode(PA3, INPUT_PULLDOWN);
  pinMode(PA4, INPUT_PULLDOWN);
  pinMode(PA5, INPUT_PULLDOWN);
  pinMode(PA6, INPUT_PULLDOWN);
  pinMode(PA7, INPUT_PULLDOWN);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  initTimerDMA();

  Serial.println("READY:STM32-UART-LA8");
}

void loop() {
  // Check for capture timeout (important for slow rates)
  if (capturing && (millis() - captureStartTime > CAPTURE_TIMEOUT_MS)) {
    Serial.println("ERROR:TIMEOUT");
    stopCapture();
  }

  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == '\r' || cmd == '\n')
      return;
    handleCommand(cmd);
  }

  if (captureComplete) {
    captureComplete = false;
    sendCapture();
    digitalWrite(LED_BUILTIN, LOW);
  }

  if (streaming && streamReadyMask != 0) {
    noInterrupts();
    uint8_t ready = streamReadyMask;
    streamReadyMask = 0;
    interrupts();

    if (ready & 0x01)
      sendStreamChunk(0);
    if (ready & 0x02)
      sendStreamChunk(1);
  }

  // Blink when idle
  static uint32_t lastBlink = 0;
  if (!capturing && !streaming && millis() - lastBlink > 500) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    lastBlink = millis();
  }
}

void handleCommand(char cmd) {
  switch (cmd) {
  case 'C':
  case 'c':
    startDMACapture();
    break;

  case 'S':
  case 's':
    startStreaming();
    break;

  case 'Q':
  case 'q':
    stopStreaming();
    Serial.println("OK:STREAM:STOP");
    break;

  case 'I':
  case 'i':
    sendInfo();
    break;

  case 'R':
  case 'r':
    stopStreaming();
    stopCapture();
    Serial.println("OK:RESET");
    break;

  case 'T':
    triggerEnabled = true;
    Serial.println("OK:TRIGGER:PA0:FALLING");
    break;

  case 'N':
    triggerEnabled = false;
    Serial.println("OK:TRIGGER:OFF");
    break;

  // === SLOW RATES (for slow signals) ===
  case 'E':
    sampleRateHz = 100; // 100Hz = 20.48 second window
    Serial.println("OK:100Hz");
    break;

  case 'D':
    sampleRateHz = 1000; // 1kHz = 2.048 second window
    Serial.println("OK:1kHz");
    break;

  case 'B':
    sampleRateHz = 10000; // 10kHz = 204.8ms window
    Serial.println("OK:10kHz");
    break;

  case 'F':
    sampleRateHz = 50000; // 50kHz = 40.96ms window
    Serial.println("OK:50kHz");
    break;

  case 'A':
    sampleRateHz = 100000; // 100kHz = 20.48ms window
    Serial.println("OK:100kHz");
    break;

  // === FAST RATES (for fast signals) ===
  case '1':
    sampleRateHz = 1000000; // 1MHz = 2.048ms window
    Serial.println("OK:1MHz");
    break;

  case '2':
    sampleRateHz = 2000000; // 2MHz = 1.024ms window
    Serial.println("OK:2MHz");
    break;

  case '5':
    sampleRateHz = 5000000; // 5MHz = 409.6µs window
    Serial.println("OK:5MHz");
    break;

  case '6':
    sampleRateHz = 6000000; // 6MHz = 341.3µs window
    Serial.println("OK:6MHz");
    break;

  default:
    Serial.println("ERROR:UNKNOWN_CMD");
  }
}

void initTimerDMA() {
  __HAL_RCC_TIM2_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 71;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

  if (HAL_TIM_Base_Init(&htim2) != HAL_OK) {
    Serial.println("ERROR:TIM_INIT");
    return;
  }

  hdma_tim2_up.Instance = DMA1_Channel2;
  hdma_tim2_up.Init.Direction = DMA_PERIPH_TO_MEMORY;
  hdma_tim2_up.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_tim2_up.Init.MemInc = DMA_MINC_ENABLE;
  hdma_tim2_up.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
  hdma_tim2_up.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
  hdma_tim2_up.Init.Mode = DMA_NORMAL;
  hdma_tim2_up.Init.Priority = DMA_PRIORITY_HIGH;

  if (HAL_DMA_Init(&hdma_tim2_up) != HAL_OK) {
    Serial.println("ERROR:DMA_INIT");
    return;
  }

  // Register callbacks
  HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_CPLT_CB_ID,
                           DMA_XferCpltCallback);
  HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_HALFCPLT_CB_ID,
                           DMA_XferHalfCallback);
  HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_ERROR_CB_ID,
                           DMA_XferErrorCallback);

  __HAL_LINKDMA(&htim2, hdma[TIM_DMA_ID_UPDATE], hdma_tim2_up);

  HAL_NVIC_SetPriority(DMA1_Channel2_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);
}

void startDMACapture() {
  if (capturing || streaming) {
    Serial.println("ERROR:BUSY");
    return;
  }

  capturing = true;
  captureComplete = false;
  captureStartTime = millis();
  digitalWrite(LED_BUILTIN, HIGH);

  if (!configureDMA(DMA_NORMAL) || !startDMA(sampleCount)) {
    capturing = false;
    digitalWrite(LED_BUILTIN, LOW);
    return;
  }

  if (triggerEnabled && !waitForPA0FallingEdge()) {
    HAL_DMA_Abort(&hdma_tim2_up);
    capturing = false;
    digitalWrite(LED_BUILTIN, LOW);
    Serial.println("ERROR:TRIGGER_TIMEOUT");
    return;
  }

  __HAL_TIM_ENABLE_DMA(&htim2, TIM_DMA_UPDATE);
  HAL_TIM_Base_Start(&htim2);
}

bool configureDMA(uint32_t mode) {
  HAL_TIM_Base_Stop(&htim2);
  __HAL_TIM_DISABLE_DMA(&htim2, TIM_DMA_UPDATE);
  HAL_DMA_Abort(&hdma_tim2_up);

  if (hdma_tim2_up.Init.Mode != mode) {
    HAL_DMA_DeInit(&hdma_tim2_up);
    hdma_tim2_up.Init.Mode = mode;
    if (HAL_DMA_Init(&hdma_tim2_up) != HAL_OK) {
      Serial.println("ERROR:DMA_INIT");
      return false;
    }

    HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_CPLT_CB_ID,
                             DMA_XferCpltCallback);
    HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_HALFCPLT_CB_ID,
                             DMA_XferHalfCallback);
    HAL_DMA_RegisterCallback(&hdma_tim2_up, HAL_DMA_XFER_ERROR_CB_ID,
                             DMA_XferErrorCallback);
  }

  uint32_t period = (72000000 / sampleRateHz) - 1;
  if (period < 11)
    period = 11;
  if (period > 65535)
    period = 65535;

  uint32_t prescaler = 0;
  if (sampleRateHz < 1100) {
    prescaler = (72000000 / (sampleRateHz * 65536)) + 1;
    period = (72000000 / (prescaler * sampleRateHz)) - 1;
  }

  __HAL_TIM_SET_PRESCALER(&htim2, prescaler);
  __HAL_TIM_SET_AUTORELOAD(&htim2, period);
  __HAL_TIM_SET_COUNTER(&htim2, 0);
  return true;
}

bool startDMA(uint32_t count) {
  uint32_t gpio_idr = (uint32_t)&(GPIOA->IDR);
  HAL_StatusTypeDef status =
      HAL_DMA_Start_IT(&hdma_tim2_up, gpio_idr, (uint32_t)samples, count);

  if (status != HAL_OK) {
    Serial.print("ERROR:DMA_START:");
    Serial.println(status);
    return false;
  }
  return true;
}

void startStreaming() {
  if (capturing || streaming) {
    Serial.println("ERROR:BUSY");
    return;
  }
  if (sampleRateHz > MAX_STREAM_RATE_HZ) {
    Serial.println("ERROR:STREAM_RATE");
    return;
  }

  streamReadyMask = 0;
  streamSequence = 0;
  streamOverruns = 0;

  if (!configureDMA(DMA_CIRCULAR) || !startDMA(BUFFER_SIZE))
    return;

  streaming = true;
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println("OK:STREAM:START");
  __HAL_TIM_ENABLE_DMA(&htim2, TIM_DMA_UPDATE);
  HAL_TIM_Base_Start(&htim2);
}

void stopStreaming() {
  if (!streaming)
    return;

  HAL_TIM_Base_Stop(&htim2);
  __HAL_TIM_DISABLE_DMA(&htim2, TIM_DMA_UPDATE);
  HAL_DMA_Abort(&hdma_tim2_up);
  streaming = false;
  streamReadyMask = 0;
  digitalWrite(LED_BUILTIN, LOW);
}

bool waitForPA0FallingEdge() {
  uint32_t startedAt = micros();

  // UART idles high. If the command arrived during a low bit, first wait
  // until the line returns high so the next falling edge is a start bit.
  while ((GPIOA->IDR & TRIGGER_PIN_MASK) == 0) {
    if ((uint32_t)(micros() - startedAt) >= TRIGGER_TIMEOUT_US)
      return false;
  }

  while ((GPIOA->IDR & TRIGGER_PIN_MASK) != 0) {
    if ((uint32_t)(micros() - startedAt) >= TRIGGER_TIMEOUT_US)
      return false;
  }

  return true;
}

void stopCapture() {
  HAL_TIM_Base_Stop(&htim2);
  __HAL_TIM_DISABLE_DMA(&htim2, TIM_DMA_UPDATE);
  HAL_DMA_Abort(&hdma_tim2_up);
  capturing = false;
  captureComplete = false;
  digitalWrite(LED_BUILTIN, LOW);
}

void DMA_XferCpltCallback(DMA_HandleTypeDef *hdma) {
  if (streaming) {
    if (streamReadyMask & 0x02)
      streamOverruns++;
    streamReadyMask |= 0x02;
    return;
  }

  HAL_TIM_Base_Stop(&htim2);
  __HAL_TIM_DISABLE_DMA(&htim2, TIM_DMA_UPDATE);

  capturing = false;
  captureComplete = true;
}

void DMA_XferHalfCallback(DMA_HandleTypeDef *hdma) {
  if (!streaming)
    return;

  if (streamReadyMask & 0x01)
    streamOverruns++;
  streamReadyMask |= 0x01;
}

void DMA_XferErrorCallback(DMA_HandleTypeDef *hdma) {
  Serial.println("ERROR:DMA_XFER");
  stopStreaming();
  stopCapture();
}

extern "C" void DMA1_Channel2_IRQHandler(void) {
  HAL_DMA_IRQHandler(&hdma_tim2_up);
}

void sendCapture() {
  Serial.print("DATA:");

  Serial.write((uint8_t)(sampleCount & 0xFF));
  Serial.write((uint8_t)((sampleCount >> 8) & 0xFF));
  Serial.write((uint8_t)((sampleCount >> 16) & 0xFF));
  Serial.write((uint8_t)((sampleCount >> 24) & 0xFF));

  Serial.write((uint8_t)(sampleRateHz & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 8) & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 16) & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 24) & 0xFF));

  Serial.write('\n');

  Serial.write(samples, sampleCount);

  Serial.println("\nEND");
}

void sendStreamChunk(uint8_t half) {
  const uint8_t *chunk = samples + (half * STREAM_CHUNK_SIZE);
  uint32_t sequence = streamSequence++;
  uint16_t crc = streamCRC16(chunk, STREAM_CHUNK_SIZE);

  Serial.write("STRM", 4);
  Serial.write((uint8_t)(STREAM_CHUNK_SIZE & 0xFF));
  Serial.write((uint8_t)((STREAM_CHUNK_SIZE >> 8) & 0xFF));
  Serial.write((uint8_t)(sampleRateHz & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 8) & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 16) & 0xFF));
  Serial.write((uint8_t)((sampleRateHz >> 24) & 0xFF));
  Serial.write((uint8_t)(sequence & 0xFF));
  Serial.write((uint8_t)((sequence >> 8) & 0xFF));
  Serial.write((uint8_t)((sequence >> 16) & 0xFF));
  Serial.write((uint8_t)((sequence >> 24) & 0xFF));
  Serial.write(chunk, STREAM_CHUNK_SIZE);
  Serial.write((uint8_t)(crc & 0xFF));
  Serial.write((uint8_t)((crc >> 8) & 0xFF));
}

uint16_t streamCRC16(const uint8_t *data, uint32_t length) {
  uint16_t crc = 0xFFFF;
  for (uint32_t i = 0; i < length; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t bit = 0; bit < 8; bit++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

void sendInfo() {
  Serial.println("INFO:STM32-UART-LA8");
  Serial.println("VERSION:4.0-MULTIRATE");
  Serial.println("CHANNELS:8");
  Serial.print("BUFFER:");
  Serial.println(BUFFER_SIZE);
  Serial.print("RATE:");
  Serial.print(sampleRateHz);
  Serial.println("Hz");
  Serial.println("RATES:100Hz,1kHz,10kHz,50kHz,100kHz,1MHz,2MHz,5MHz,6MHz");
  Serial.print("TRIGGER:");
  Serial.println(triggerEnabled ? "PA0:FALLING" : "OFF");
  Serial.print("STREAM_MAX:");
  Serial.println(MAX_STREAM_RATE_HZ);
  Serial.print("STREAM_OVERRUNS:");
  Serial.println(streamOverruns);
  Serial.println("MAX:6MHz");
  Serial.print("STATUS:");
  Serial.println(capturing || streaming ? "BUSY" : "READY");
}
