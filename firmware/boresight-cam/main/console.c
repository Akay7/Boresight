/*
 * Emulator build only: the buttons, operated from the serial console.
 *
 *   press     the trigger goes down, as if its pin were pulled low
 *   release   the trigger comes back up
 *   click     press, hold past the debounce, release
 *
 * Each command sets the level the button task reads in place of the pin,
 * so the debouncer, the press/release logic and the send path are the
 * real ones. Only reading the pin is replaced.
 */
#include <stdio.h>
#include <string.h>

#include "boresight_cam.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "esp_log.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "console";

/* s_buttons[0] in buttons.c. */
#define TRIGGER_INDEX 0

static void console_task(void *arg)
{
    (void)arg;
    char line[64];
    for (;;) {
        if (fgets(line, sizeof line, stdin) == NULL) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        line[strcspn(line, "\r\n")] = '\0';
        if (strcmp(line, "press") == 0) {
            ESP_LOGI(TAG, "trigger pressed");
            buttons_inject(TRIGGER_INDEX, true);
        } else if (strcmp(line, "release") == 0) {
            ESP_LOGI(TAG, "trigger released");
            buttons_inject(TRIGGER_INDEX, false);
        } else if (strcmp(line, "click") == 0) {
            ESP_LOGI(TAG, "trigger clicked");
            buttons_inject(TRIGGER_INDEX, true);
            vTaskDelay(pdMS_TO_TICKS(CONFIG_BORESIGHT_DEBOUNCE_MS * 5));
            buttons_inject(TRIGGER_INDEX, false);
        } else if (line[0] != '\0') {
            ESP_LOGW(TAG, "unknown command \"%s\": press, release or click", line);
        }
    }
}

void console_start(void)
{
    /* With the driver installed, reads from stdin block until a line
     * arrives instead of returning whatever partial input is there. */
    uart_driver_install(CONFIG_ESP_CONSOLE_UART_NUM, 256, 0, 0, NULL, 0);
    uart_vfs_dev_use_driver(CONFIG_ESP_CONSOLE_UART_NUM);
    setvbuf(stdin, NULL, _IONBF, 0);
    xTaskCreate(console_task, "console", 3072, NULL, 3, NULL);
    ESP_LOGI(TAG, "buttons on the console: press, release, click");
}
