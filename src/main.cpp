#include <Arduino.h>

void handleCommand(char cmd);
void initTimerDMA();
void startDMACapture();
void stopCapture();
void DMA_XferCpltCallback(DMA_HandleTypeDef *hdma);
void DMA_XferErrorCallback(DMA_HandleTypeDef *hdma);
void sendCapture();
void sendInfo();

#include "../firmware/stm32_logic_analyzer/stm32_logic_analyzer.ino"
