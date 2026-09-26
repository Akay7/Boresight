/*
 * Emulator build only: the network over QEMU's emulated OpenCores Ethernet
 * MAC, in place of the Wi-Fi radio QEMU does not emulate.
 *
 * Addresses come from QEMU's user-mode network by DHCP. From in here the
 * machine running QEMU is 10.0.2.2, which is where the emulator profile
 * points the server address. Everything that waits on "connected" -- the
 * link task -- is the same code as on a board.
 */
#include "boresight_cam.h"
#include "esp_check.h"
#include "esp_eth.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "freertos/event_groups.h"

static const char *TAG = "network";

#define CONNECTED_BIT BIT0

static EventGroupHandle_t s_events;

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == ETH_EVENT && id == ETHERNET_EVENT_DISCONNECTED) {
        xEventGroupClearBits(s_events, CONNECTED_BIT);
        ESP_LOGW(TAG, "emulated Ethernet link down");
    } else if (base == IP_EVENT && id == IP_EVENT_ETH_GOT_IP) {
        const ip_event_got_ip_t *event = data;
        ESP_LOGI(TAG, "emulated Ethernet up as " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_events, CONNECTED_BIT);
    }
}

esp_err_t network_start(void)
{
    s_events = xEventGroupCreate();
    if (s_events == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop");

    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    esp_netif_t *netif = esp_netif_new(&netif_config);

    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    /* QEMU's PHY has nothing to negotiate. */
    phy_config.autonego_timeout_ms = 100;
    esp_eth_mac_t *mac = esp_eth_mac_new_openeth(&mac_config);
    esp_eth_phy_t *phy = esp_eth_phy_new_dp83848(&phy_config);
    if (mac == NULL || phy == NULL) {
        ESP_LOGE(TAG, "could not create the emulated Ethernet MAC or PHY");
        return ESP_FAIL;
    }

    esp_eth_config_t config = ETH_DEFAULT_CONFIG(mac, phy);
    esp_eth_handle_t handle = NULL;
    ESP_RETURN_ON_ERROR(esp_eth_driver_install(&config, &handle), TAG, "driver");
    ESP_RETURN_ON_ERROR(esp_netif_attach(netif, esp_eth_new_netif_glue(handle)), TAG,
                        "netif attach");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, on_event, NULL), TAG,
        "eth handler");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, on_event, NULL),
        TAG, "ip handler");
    ESP_RETURN_ON_ERROR(esp_eth_start(handle), TAG, "start");
    return ESP_OK;
}

bool network_wait_connected(TickType_t timeout)
{
    return (xEventGroupWaitBits(s_events, CONNECTED_BIT, pdFALSE, pdTRUE, timeout) &
            CONNECTED_BIT) != 0;
}
