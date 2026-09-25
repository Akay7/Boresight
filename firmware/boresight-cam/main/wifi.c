#include <inttypes.h>
#include <string.h>

#include "boresight_cam.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "sdkconfig.h"

static const char *TAG = "wifi";

#define CONNECTED_BIT BIT0

static EventGroupHandle_t s_events;
static esp_timer_handle_t s_retry_timer;
static uint32_t s_backoff_ms;

static void retry(void *arg)
{
    (void)arg;
    esp_wifi_connect();
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = data;
        xEventGroupClearBits(s_events, CONNECTED_BIT);
        s_backoff_ms = bp_backoff_next(s_backoff_ms);
        if (event->reason == WIFI_REASON_AUTH_FAIL ||
            event->reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT) {
            ESP_LOGE(TAG, "rejected by \"%s\": check the Wi-Fi password",
                     CONFIG_BORESIGHT_WIFI_SSID);
        } else if (event->reason == WIFI_REASON_NO_AP_FOUND) {
            ESP_LOGW(TAG, "\"%s\" not found (the ESP32 sees 2.4 GHz only)",
                     CONFIG_BORESIGHT_WIFI_SSID);
        }
        ESP_LOGW(TAG, "not connected (reason %d), retrying in %" PRIu32 " ms",
                 event->reason, s_backoff_ms);
        esp_timer_start_once(s_retry_timer, (uint64_t)s_backoff_ms * 1000u);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = data;
        s_backoff_ms = 0;
        ESP_LOGI(TAG, "joined \"%s\" as " IPSTR, CONFIG_BORESIGHT_WIFI_SSID,
                 IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_events, CONNECTED_BIT);
    }
}

esp_err_t wifi_start(void)
{
    s_events = xEventGroupCreate();
    if (s_events == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop");
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "wifi init");

    const esp_timer_create_args_t timer = {.callback = retry, .name = "wifi_retry"};
    ESP_RETURN_ON_ERROR(esp_timer_create(&timer, &s_retry_timer), TAG, "timer");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL),
        TAG, "wifi handler");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL),
        TAG, "ip handler");

    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, CONFIG_BORESIGHT_WIFI_SSID,
            sizeof config.sta.ssid);
    strlcpy((char *)config.sta.password, CONFIG_BORESIGHT_WIFI_PASSWORD,
            sizeof config.sta.password);
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "config");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "start");

    /* Modem sleep batches traffic around the access point's beacon
     * interval: tens to hundreds of milliseconds added to every frame and
     * every trigger press. A light gun cannot afford it. */
    esp_wifi_set_ps(WIFI_PS_NONE);
    return ESP_OK;
}

bool wifi_wait_connected(TickType_t timeout)
{
    return (xEventGroupWaitBits(s_events, CONNECTED_BIT, pdFALSE, pdTRUE, timeout) &
            CONNECTED_BIT) != 0;
}
