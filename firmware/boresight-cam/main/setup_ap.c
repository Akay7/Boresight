/*
 * Setup mode's network on a board: an open access point of the device's
 * own, a list of the networks it can see, and a name server that answers
 * every lookup with the device's address so a phone's sign-in check lands
 * on the setup page.
 *
 * APSTA rather than AP: the station half is what scans. Nothing here
 * joins another network.
 */
#include <string.h>

#include "boresight_cam.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

static const char *TAG = "setup_ap";

#define SETUP_CHANNEL 1
#define SETUP_MAX_STATIONS 2
#define DNS_PORT 53

/* The address the stock DHCP server gives the access point itself. */
static const uint8_t SETUP_IP[4] = {192, 168, 4, 1};

static char s_networks[SETUP_MAX_NETWORKS][BP_SSID_MAX + 1];
static size_t s_network_count;
static SemaphoreHandle_t s_networks_lock;

static void scan(void)
{
    /* Blocking, a second or two. The access point may drop off its
     * channel meanwhile; a phone already joined rides it out. */
    if (esp_wifi_scan_start(NULL, true) != ESP_OK) {
        ESP_LOGW(TAG, "network scan failed");
        return;
    }
    uint16_t found = 24;
    wifi_ap_record_t records[24];
    if (esp_wifi_scan_get_ap_records(&found, records) != ESP_OK) {
        return;
    }
    xSemaphoreTake(s_networks_lock, portMAX_DELAY);
    s_network_count = 0;
    /* Strongest first, as the driver sorts them; each name once. */
    for (uint16_t i = 0; i < found && s_network_count < SETUP_MAX_NETWORKS; i++) {
        const char *ssid = (const char *)records[i].ssid;
        if (ssid[0] == '\0') {
            continue; /* hidden */
        }
        bool seen = false;
        for (size_t j = 0; j < s_network_count && !seen; j++) {
            seen = strcmp(s_networks[j], ssid) == 0;
        }
        if (!seen) {
            strlcpy(s_networks[s_network_count++], ssid, BP_SSID_MAX + 1);
        }
    }
    xSemaphoreGive(s_networks_lock);
    ESP_LOGI(TAG, "%u network(s) in range", (unsigned)s_network_count);
}

size_t setup_networks(char names[][BP_SSID_MAX + 1], size_t max)
{
    xSemaphoreTake(s_networks_lock, portMAX_DELAY);
    size_t count = s_network_count < max ? s_network_count : max;
    memcpy(names, s_networks, count * sizeof s_networks[0]);
    xSemaphoreGive(s_networks_lock);
    return count;
}

void setup_rescan(void)
{
    scan();
}

static void dns_task(void *arg)
{
    (void)arg;
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in bind_to = {
        .sin_family = AF_INET,
        .sin_port = htons(DNS_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    if (sock < 0 || bind(sock, (struct sockaddr *)&bind_to, sizeof bind_to) != 0) {
        ESP_LOGE(TAG, "name server could not bind port %d", DNS_PORT);
        vTaskDelete(NULL);
        return;
    }
    uint8_t query[512];
    uint8_t reply[512];
    for (;;) {
        struct sockaddr_in from;
        socklen_t from_length = sizeof from;
        int length = recvfrom(sock, query, sizeof query, 0, (struct sockaddr *)&from,
                              &from_length);
        if (length <= 0) {
            continue;
        }
        int reply_length =
            bp_dns_answer(query, (size_t)length, SETUP_IP, reply, sizeof reply);
        if (reply_length > 0) {
            sendto(sock, reply, (size_t)reply_length, 0, (struct sockaddr *)&from,
                   from_length);
        }
    }
}

esp_err_t setup_network_start(char *name, size_t size)
{
    s_networks_lock = xSemaphoreCreateMutex();
    if (s_networks_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop");
    esp_netif_create_default_wifi_ap();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "wifi init");

    uint8_t mac[6];
    ESP_RETURN_ON_ERROR(esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP), TAG, "mac");
    snprintf(name, size, "Boresight-%02X%02X", mac[4], mac[5]);

    wifi_config_t ap = {
        .ap = {
            .channel = SETUP_CHANNEL,
            .authmode = WIFI_AUTH_OPEN,
            .max_connection = SETUP_MAX_STATIONS,
        },
    };
    strlcpy((char *)ap.ap.ssid, name, sizeof ap.ap.ssid);
    ap.ap.ssid_len = (uint8_t)strlen(name);

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_APSTA), TAG, "mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_AP, &ap), TAG, "ap config");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "start");
    scan();

    if (xTaskCreate(dns_task, "setup_dns", 4096, NULL, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "setup network \"%s\" open (no password) at %d.%d.%d.%d", name,
             SETUP_IP[0], SETUP_IP[1], SETUP_IP[2], SETUP_IP[3]);
    return ESP_OK;
}

void setup_network_stop(void)
{
    esp_wifi_stop();
    ESP_LOGI(TAG, "setup network closed");
}
