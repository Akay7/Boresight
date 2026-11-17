/*
 * Setup mode: decided once at boot, before the camera starts, and left
 * only by restarting, so normal operation always begins from a clean boot.
 *
 * On a board it opens a network of its own (setup_ap.c); in the emulator
 * it serves the same page over the emulated Ethernet, since QEMU has no
 * radio. Either way the network lasts at most SETUP_LIFETIME_MS: a save or
 * a reset restarts sooner, and running out restarts a configured device
 * into normal operation and parks an unconfigured one on the error
 * pattern.
 */
#include <string.h>

#include "boresight_cam.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "setup";

#define SETUP_LIFETIME_MS (10u * 60u * 1000u)
/* Long enough for the confirmation page to reach the phone first. */
#define RESTART_DELAY_MS 1500u
#define DONE_BIT BIT0

/* The trigger held from boot for this long opens setup mode. */
#define HOLD_MS 5000u
#define HOLD_SAMPLE_MS 20u
/* A release must last this long to count, so contact bounce in a hold
 * does not end it. */
#define HOLD_RELEASE_MS 60u

static EventGroupHandle_t s_events;

void setup_done(void)
{
    if (s_events != NULL) {
        xEventGroupSetBits(s_events, DONE_BIT);
    }
}

#if CONFIG_BORESIGHT_EMULATOR
/* No radio in QEMU: no networks to list. */
size_t setup_networks(char names[][BP_SSID_MAX + 1], size_t max)
{
    (void)names;
    (void)max;
    return 0;
}

void setup_rescan(void)
{
}
#endif

/* Configured enough to leave setup mode for normal operation. */
static bool configured(void)
{
#if CONFIG_BORESIGHT_EMULATOR
    return settings()->host[0] != '\0';
#else
    return settings()->ssid[0] != '\0';
#endif
}

bool setup_requested_at_boot(void)
{
    if (settings_take_setup_request()) {
        ESP_LOGI(TAG, "setup mode requested from the console");
        return true;
    }
#if CONFIG_BORESIGHT_EMULATOR
    return false;
#else
    if (!configured()) {
        ESP_LOGW(TAG, "no Wi-Fi network configured: opening setup mode");
        return true;
    }

    /* The trigger, read directly: the button task is not running, and
     * will not be if setup mode opens. Active-low with the pull-up, as
     * buttons.c wires it. */
    const gpio_num_t pin = (gpio_num_t)CONFIG_BORESIGHT_TRIGGER_GPIO;
    gpio_reset_pin(pin);
    gpio_set_direction(pin, GPIO_MODE_INPUT);
    gpio_set_pull_mode(pin, GPIO_PULLUP_ONLY);
    vTaskDelay(pdMS_TO_TICKS(5)); /* let the pull-up charge the line */
    if (gpio_get_level(pin) != 0) {
        return false;
    }

    ESP_LOGI(TAG, "trigger held at boot: keep holding for %u s to open setup mode",
             HOLD_MS / 1000u);
    const uint32_t start = boresight_now_ms();
    uint32_t released_since = 0;
    bool released = false;
    while (boresight_now_ms() - start < HOLD_MS) {
        vTaskDelay(pdMS_TO_TICKS(HOLD_SAMPLE_MS));
        const uint32_t now = boresight_now_ms();
        if (gpio_get_level(pin) != 0) {
            if (!released) {
                released = true;
                released_since = now;
            } else if (now - released_since >= HOLD_RELEASE_MS) {
                ESP_LOGI(TAG, "trigger released early: starting normally");
                return false;
            }
        } else {
            released = false;
        }
    }
    /* Shown the moment the hold is long enough, so it can be let go. */
    status_led_set_link(BP_LINK_SETUP);
    ESP_LOGI(TAG, "trigger held for %u s: opening setup mode", HOLD_MS / 1000u);
    return true;
#endif
}

void setup_run(void)
{
    status_led_set_link(BP_LINK_SETUP);
    s_events = xEventGroupCreate();
    if (s_events == NULL) {
        ESP_LOGE(TAG, "no memory for setup mode");
        status_led_set_link(BP_LINK_ERROR);
        return;
    }

#if CONFIG_BORESIGHT_EMULATOR
    if (network_start() != ESP_OK || !network_wait_connected(pdMS_TO_TICKS(30000))) {
        ESP_LOGE(TAG, "the emulated network did not come up");
        status_led_set_link(BP_LINK_ERROR);
        return;
    }
    const char *home = "/";
#else
    char name[24];
    if (setup_network_start(name, sizeof name) != ESP_OK) {
        ESP_LOGE(TAG, "the setup network did not start");
        status_led_set_link(BP_LINK_ERROR);
        return;
    }
    /* Absolute: a sign-in check asked for some other host, and must be
     * sent to this one. */
    const char *home = "http://192.168.4.1/";
#endif
    if (setup_http_start(home) != ESP_OK) {
        status_led_set_link(BP_LINK_ERROR);
        return;
    }
    /* Setup mode is up: a newly installed firmware that gets this far can
     * always be replaced again, so it is kept. */
    ota_mark_good();
    ESP_LOGI(TAG, "setup mode: closes when settings are saved, or in %u minutes",
             SETUP_LIFETIME_MS / 60000u);

    const EventBits_t bits = xEventGroupWaitBits(s_events, DONE_BIT, pdTRUE, pdTRUE,
                                                 pdMS_TO_TICKS(SETUP_LIFETIME_MS));
    if (bits & DONE_BIT) {
        vTaskDelay(pdMS_TO_TICKS(RESTART_DELAY_MS));
        ESP_LOGI(TAG, "leaving setup mode: restarting");
        boresight_restart();
    }

    ESP_LOGW(TAG, "setup mode ran out after %u minutes with nothing saved",
             SETUP_LIFETIME_MS / 60000u);
    setup_http_stop();
#if !CONFIG_BORESIGHT_EMULATOR
    setup_network_stop();
#endif
    if (configured()) {
        ESP_LOGI(TAG, "restarting with the settings unchanged");
        boresight_restart();
    }
    ESP_LOGE(TAG, "still not configured: reset or power-cycle the board to open "
                  "setup mode again");
    status_led_set_link(BP_LINK_ERROR);
}
