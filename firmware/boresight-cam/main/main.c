/*
 * Boresight ESP32-CAM: the barrel camera and physical trigger.
 *
 * Streams frames to the Boresight server's existing frame socket in the
 * same wire format the phone client uses, and sends the existing trigger
 * message when the trigger button is pressed. Nothing on the server knows
 * or cares that this is not a phone.
 */
#include <inttypes.h>
#include <string.h>

#include "boresight_cam.h"
#include <stdio.h>

#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

static const char *TAG = "boresight";

#if CONFIG_BORESIGHT_EMULATOR
/* On every version this image reports, so a session on the server can
 * never be mistaken for a board. */
#define VERSION_SUFFIX "+emulator"
#else
#define VERSION_SUFFIX ""
#endif

/* Same cadence as the server's own session log line. */
#define LOG_INTERVAL_MS 5000u

uint32_t boresight_now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
    case ESP_RST_POWERON:
        return "power-on";
    case ESP_RST_SW:
        return "software reset";
    case ESP_RST_PANIC:
        return "panic";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:
        return "watchdog";
    case ESP_RST_BROWNOUT:
        return "brown-out";
    case ESP_RST_DEEPSLEEP:
        return "deep sleep";
    case ESP_RST_EXT:
        return "external pin";
    default:
        return "other";
    }
}

static bool configuration_complete(void)
{
    /* Kconfig cannot mark a string as required, and failing the build
     * would break building a fresh checkout at all, so it is checked here,
     * where the log says exactly what is missing. */
    bool complete = true;
#if !CONFIG_BORESIGHT_EMULATOR
    if (strlen(CONFIG_BORESIGHT_WIFI_SSID) == 0) {
        ESP_LOGE(TAG, "not configured: Wi-Fi SSID "
                      "(idf.py menuconfig -> Boresight camera -> Network)");
        complete = false;
    }
#endif
    if (strlen(CONFIG_BORESIGHT_SERVER_HOST) == 0) {
        ESP_LOGE(TAG, "not configured: server address "
                      "(the \"host\" line the server prints at startup)");
        complete = false;
    }
    if (strlen(CONFIG_BORESIGHT_TOKEN) == 0) {
        ESP_LOGW(TAG, "no token configured: a server bound to a network "
                      "address will refuse the connection");
    }
    return complete;
}

/* Stops here with the error pattern showing. The LED task keeps running;
 * nothing else does until the board is reset. */
static void halt(const char *why)
{
    ESP_LOGE(TAG, "not streaming: %s", why);
    status_led_set_link(BP_LINK_ERROR);
    vTaskDelete(NULL);
}

static void capture_task(void *arg)
{
    (void)arg;
    const TickType_t period = pdMS_TO_TICKS(1000 / CONFIG_BORESIGHT_MAX_FPS);
    TickType_t wake = xTaskGetTickCount();
    uint32_t sent = 0;
    uint32_t skipped = 0;
    uint32_t window_start = boresight_now_ms();

    for (;;) {
        link_service();

        if (!link_is_streaming()) {
            vTaskDelay(pdMS_TO_TICKS(50));
            wake = xTaskGetTickCount();
            continue;
        }

        /* The newest frame, with nothing older waiting behind it: the
         * sensor's driver runs in CAMERA_GRAB_LATEST mode -- the device-side
         * equivalent of the server's newest-wins slot. */
        camera_frame_t frame;
        if (!camera_grab(&frame)) {
            skipped++;
        } else {
            if (link_send_frame(frame.captured_ms, frame.data, frame.length,
                                CONFIG_BORESIGHT_SEND_TIMEOUT_MS) == ESP_OK) {
                sent++;
            } else {
                /* Never retried: by the time it could go, a fresher frame
                 * exists. */
                skipped++;
            }
            camera_release(&frame);
        }

        uint32_t now = boresight_now_ms();
        if (now - window_start >= LOG_INTERVAL_MS) {
            ESP_LOGI(TAG,
                     "streaming: %.1f fps sent, %" PRIu32 " skipped, "
                     "rtt %.0f ms, %" PRIu32 " KB heap free",
                     sent * 1000.0 / (now - window_start), skipped,
                     link_rtt_ms(), esp_get_free_heap_size() / 1024);
            sent = 0;
            skipped = 0;
            window_start = now;
        }

        /* The rate cap. After a stall (a reconnect, a slow send) the
         * schedule is reset rather than caught up, or the cap would be
         * exceeded in a burst. */
        if (xTaskDelayUntil(&wake, period) == pdFALSE) {
            wake = xTaskGetTickCount();
        }
    }
}

void app_main(void)
{
    static char version[48];
    snprintf(version, sizeof version, "%s%s", esp_app_get_description()->version,
             VERSION_SUFFIX);
    esp_reset_reason_t reason = esp_reset_reason();
    ESP_LOGI(TAG, "Boresight camera %s, reset reason: %s", version,
             reset_reason_name(reason));
#if CONFIG_BORESIGHT_EMULATOR
    ESP_LOGW(TAG, "EMULATOR BUILD: recorded frames for a camera, emulated "
                  "Ethernet for Wi-Fi, console commands for buttons. This "
                  "image does not run on an ESP32-CAM.");
#endif
    if (reason == ESP_RST_BROWNOUT) {
        /* The camera and the Wi-Fi radio draw current in bursts. On a weak
         * supply that looks like random reboots unless it is named. */
        ESP_LOGW(TAG, "the supply voltage sagged: use a 5 V supply of at "
                      "least 1 A, not a computer's USB port through an "
                      "adapter board");
    }

    status_led_start();

    if (!configuration_complete()) {
        halt("configuration incomplete");
        return;
    }
    if (!buttons_valid()) {
        halt("a button is configured on a pin this board cannot spare");
        return;
    }

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        halt("NVS (needed by Wi-Fi) did not initialise");
        return;
    }

    int width = 0;
    int height = 0;
    if (camera_start(&width, &height) != ESP_OK) {
        halt("the camera did not start; check the ribbon cable is seated");
        return;
    }
    /* After the camera: its driver installs the shared GPIO interrupt
     * service with the flags it needs. */
    if (buttons_start() != ESP_OK) {
        halt("the buttons could not be set up");
        return;
    }
#if CONFIG_BORESIGHT_EMULATOR
    console_start();
#endif
    if (network_start() != ESP_OK) {
        halt("the network did not start");
        return;
    }
    if (link_start(version, width, height) != ESP_OK) {
        halt("the server connection could not be set up");
        return;
    }

    /* Core 1, away from the Wi-Fi stack on core 0. */
    if (xTaskCreatePinnedToCore(capture_task, "capture", 4096, NULL, 5, NULL,
                                1) != pdPASS) {
        halt("no memory for the capture task");
    }
}
