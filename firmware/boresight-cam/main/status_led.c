/*
 * The on-board red LED (GPIO33, active-low): the only display this device
 * has. Patterns are defined, and tested, in boresight_proto.
 */
#include "boresight_cam.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#define TICK_MS 10

static const char *TAG = "status";

static volatile bp_link_state_t s_state = BP_LINK_JOINING_WIFI;
static volatile bool s_solved;
static volatile bool s_have_stats;
static volatile uint32_t s_stats_at_ms;

static const char *state_name(bp_link_state_t state)
{
    switch (state) {
    case BP_LINK_JOINING_WIFI:
        return "joining network";
    case BP_LINK_CONNECTING:
        return "connecting";
    case BP_LINK_ERROR:
        return "error";
    case BP_LINK_STREAMING:
        return "streaming";
    default:
        return "unknown";
    }
}

void status_led_set_link(bp_link_state_t state)
{
    /* Logged as well as shown: with a serial cable, or in the emulator,
     * the state can be read and waited on rather than squinted at. */
    if (state != s_state) {
        ESP_LOGI(TAG, "state: %s", state_name(state));
    }
    s_state = state;
}

void status_led_report_stats(bool solved)
{
    s_stats_at_ms = boresight_now_ms();
    s_solved = solved;
    s_have_stats = true;
}

static void led_task(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t now = boresight_now_ms();
        uint32_t age = s_have_stats ? now - s_stats_at_ms : UINT32_MAX;
        bool on = bp_led_on(bp_led_pattern(s_state, s_solved, age), now);
        gpio_set_level(CONFIG_BORESIGHT_STATUS_LED_GPIO, on ? 0 : 1);
        vTaskDelay(pdMS_TO_TICKS(TICK_MS));
    }
}

void status_led_start(void)
{
    gpio_reset_pin(CONFIG_BORESIGHT_STATUS_LED_GPIO);
    gpio_set_direction(CONFIG_BORESIGHT_STATUS_LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(CONFIG_BORESIGHT_STATUS_LED_GPIO, 1);
    ESP_LOGI(TAG, "state: %s", state_name(s_state));
    xTaskCreate(led_task, "status_led", 2048, NULL, 2, NULL);
}
