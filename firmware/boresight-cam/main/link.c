/*
 * The frame socket.
 *
 * One task owns the connection's life: wait for Wi-Fi, connect, send
 * hello, wait for the end, tear down, back off, repeat. The client's own
 * auto-reconnect is off, because a refused token has to back off for long
 * and show an error rather than retry every second like a network blip.
 *
 * Sends from the capture and button tasks are serialised by s_lock, which
 * also keeps anything from landing between the fragments of a frame.
 */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "boresight_cam.h"
#include "cJSON.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_websocket_client.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "mbedtls/x509.h"
#include "mbedtls/x509_crt.h"
#include "sdkconfig.h"
#if !CONFIG_BORESIGHT_EMULATOR
#include "esp_netif_ip_addr.h"
#include "mdns.h"
#endif

static const char *TAG = "link";

#define FRAME_SOCKET_PATH "/ws/frames"
#define CONNECTED_BIT BIT0
#define ENDED_BIT BIT1
#define CONNECT_TIMEOUT_MS 15000
#define HELLO_TIMEOUT_MS 1000
#define RTT_REPORT_INTERVAL_MS 1000u
#define WS_POLICY_VIOLATION 1008

#if CONFIG_BORESIGHT_TLS
#define SCHEME "wss"
extern const char server_cert_pem_start[] asm("_binary_server_cert_pem_start");
#else
#define SCHEME "ws"
#endif

typedef enum {
    FAILURE_NONE = 0,
    /* The server would not have this device: wrong or missing token. */
    FAILURE_REJECTED,
    /* The server is not the one whose certificate was built in. */
    FAILURE_CERTIFICATE,
} failure_t;

static EventGroupHandle_t s_events;
static SemaphoreHandle_t s_lock;
static esp_websocket_client_handle_t s_client; /* guarded by s_lock */
/* The header stamp of the last frame sent on this connection, which a
 * trigger press names. Guarded by s_lock; reset per connection, since a
 * frame the previous session sent is nothing the new one has seen. */
static bool s_frame_sent;
static double s_last_frame_ms;
static volatile bool s_streaming;
static volatile uint32_t s_session_id;
static volatile failure_t s_failure;

static char s_uri[320];
static char s_hello[160];

/* Receive side: touched only from the client's own task. */
static char s_rx[1024];
static bool s_rx_skipping;
static bool s_warned_oversize;
static int s_last_triggers = -1;
static uint32_t s_last_rtt_report_ms;

/* Handed from the client's task to the capture task. Sending from the
 * event handler itself could deadlock against a frame send holding
 * s_lock while it waits for the client's internal lock. */
static portMUX_TYPE s_rtt_mux = portMUX_INITIALIZER_UNLOCKED;
static bool s_rtt_pending;
static double s_rtt_ms;

/* --- Receive ------------------------------------------------------------ */

static void on_text(const char *text)
{
    cJSON *root = cJSON_Parse(text);
    if (root == NULL) {
        return;
    }
    const cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    if (cJSON_IsString(type) && strcmp(type->valuestring, "stats") == 0) {
        const cJSON *client_ms = cJSON_GetObjectItemCaseSensitive(root, "client_ms");
        const cJSON *outcome = cJSON_GetObjectItemCaseSensitive(root, "outcome");
        const cJSON *triggers = cJSON_GetObjectItemCaseSensitive(root, "triggers");

        /* Only a report for a processed frame echoes a timestamp; one for a
         * malformed frame says nothing about the markers. */
        if (cJSON_IsNumber(client_ms)) {
            double rtt = (double)esp_timer_get_time() / 1000.0 - client_ms->valuedouble;
            uint32_t now = boresight_now_ms();
            portENTER_CRITICAL(&s_rtt_mux);
            s_rtt_ms = rtt;
            if (now - s_last_rtt_report_ms >= RTT_REPORT_INTERVAL_MS) {
                s_last_rtt_report_ms = now;
                s_rtt_pending = true;
            }
            portEXIT_CRITICAL(&s_rtt_mux);
            status_led_report_stats(cJSON_IsString(outcome) &&
                                    strcmp(outcome->valuestring, "solved") == 0);
        }
        if (cJSON_IsNumber(triggers) && triggers->valueint != s_last_triggers) {
            s_last_triggers = triggers->valueint;
            ESP_LOGI(TAG, "server has counted %d trigger press(es)", s_last_triggers);
        }
    }
    cJSON_Delete(root);
}

static void on_data(const esp_websocket_event_data_t *data)
{
    switch (data->op_code) {
    case 0x08: /* close: the status code is the first two bytes, big-endian */
        if (data->data_len >= 2) {
            int code = ((uint8_t)data->data_ptr[0] << 8) | (uint8_t)data->data_ptr[1];
            if (code == WS_POLICY_VIOLATION) {
                ESP_LOGE(TAG, "server closed the socket as a policy violation: "
                              "check the token");
                s_failure = FAILURE_REJECTED;
            } else {
                ESP_LOGI(TAG, "server closed the socket (%d)", code);
            }
        }
        return;
    case 0x01: /* text */
        break;
    default: /* binary, ping, pong: nothing the server sends us */
        return;
    }

    if (data->payload_offset + data->data_len > data->payload_len) {
        return;
    }
    if (data->payload_offset == 0) {
        /* Frame reports are a few hundred bytes. Anything larger carries
         * debug geometry some phone turned on, which this device cannot use
         * and should not spend heap assembling. */
        s_rx_skipping = data->payload_len >= (int)sizeof s_rx;
        if (s_rx_skipping && !s_warned_oversize) {
            s_warned_oversize = true;
            ESP_LOGW(TAG, "ignoring %d-byte telemetry: debug geometry is probably "
                          "on; LED and round-trip reports pause until it is off",
                     data->payload_len);
        }
    }
    if (s_rx_skipping) {
        return;
    }
    memcpy(s_rx + data->payload_offset, data->data_ptr, data->data_len);
    if (data->payload_offset + data->data_len == data->payload_len) {
        s_rx[data->payload_len] = '\0';
        on_text(s_rx);
    }
}

static void note_error(const esp_websocket_event_data_t *data)
{
    const esp_websocket_error_codes_t *error = &data->error_handle;
    /* Keyed on the status itself, not on error_type: the client reports a
     * refused handshake as a transport failure that carries the HTTP status
     * (found in emulation, where a 403 was otherwise retried as a blip). */
    int status = error->esp_ws_handshake_status_code;
    if (status == 401 || status == 403) {
        /* The server refuses a bad token before accepting the socket, which
         * reaches the client as an HTTP status, not a close code. */
        ESP_LOGE(TAG, "server refused the connection (HTTP %d): check the token",
                 status);
        s_failure = FAILURE_REJECTED;
#if CONFIG_BORESIGHT_TLS
    } else if (error->esp_tls_stack_err == MBEDTLS_ERR_X509_CERT_VERIFY_FAILED) {
        /* Only the TLS stack's own verdict. The verify-flags field is not
         * meaningful outside a TLS failure: on a plain connection reset it
         * held 0x3ffc1ff0 (found in emulation), which read as a certificate
         * mismatch and turned every server restart into a 30 s error. */
        ESP_LOGE(TAG, "the server's certificate is not the one built into this "
                      "firmware (verify flags 0x%x); re-copy "
                      ".boresight/cert.pem and rebuild",
                 error->esp_tls_cert_verify_flags);
        s_failure = FAILURE_CERTIFICATE;
#endif
    } else if (status != 0) {
        ESP_LOGW(TAG, "handshake failed (HTTP %d): is this the Boresight "
                      "server and port?",
                 status);
    } else {
        ESP_LOGW(TAG, "socket error (type %d): %s (errno %d)", (int)error->error_type,
                 esp_err_to_name(error->esp_tls_last_esp_err),
                 error->esp_transport_sock_errno);
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *event_data)
{
    (void)arg;
    (void)base;
    const esp_websocket_event_data_t *data = event_data;
    switch (id) {
    case WEBSOCKET_EVENT_CONNECTED:
        xEventGroupSetBits(s_events, CONNECTED_BIT);
        break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
        xEventGroupSetBits(s_events, ENDED_BIT);
        break;
    case WEBSOCKET_EVENT_ERROR:
        note_error(data);
        break;
    case WEBSOCKET_EVENT_DATA:
        on_data(data);
        break;
    default:
        break;
    }
}

/* --- Send --------------------------------------------------------------- */

bool link_is_streaming(void)
{
    return s_streaming;
}

uint32_t link_session_id(void)
{
    return s_session_id;
}

esp_err_t link_send_text(const char *text, uint32_t timeout_ms)
{
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t result = ESP_ERR_INVALID_STATE;
    if (s_streaming && s_client != NULL) {
        int sent = esp_websocket_client_send_text(s_client, text, (int)strlen(text),
                                                  pdMS_TO_TICKS(timeout_ms));
        result = sent < 0 ? ESP_FAIL : ESP_OK;
    }
    xSemaphoreGive(s_lock);
    return result;
}

esp_err_t link_send_frame(double client_ms, const uint8_t *jpeg, size_t length,
                          uint32_t timeout_ms)
{
    TickType_t timeout = pdMS_TO_TICKS(timeout_ms);
    if (xSemaphoreTake(s_lock, timeout) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t result = ESP_ERR_INVALID_STATE;
    if (s_streaming && s_client != NULL) {
        uint8_t header[BP_HEADER_SIZE];
        bp_pack_header(client_ms, header);
        /* Header and JPEG as fragments of one binary message, rather than
         * copying tens of kilobytes into a new buffer per frame. The server
         * reassembles fragments; what it receives is identical. */
        if (esp_websocket_client_send_bin_partial(s_client, (const char *)header,
                                                  BP_HEADER_SIZE, timeout) < 0) {
            /* Nothing reached the wire: this frame is simply skipped. */
            result = ESP_ERR_TIMEOUT;
        } else if (esp_websocket_client_send_cont_msg(s_client, (const char *)jpeg,
                                                      (int)length, timeout) < 0 ||
                   esp_websocket_client_send_fin(s_client, timeout) < 0) {
            /* Half a message is on the wire and can be neither finished nor
             * retracted, so the stream is unusable: end the session. */
            ESP_LOGW(TAG, "frame send broke off mid-message; reconnecting");
            s_streaming = false;
            xEventGroupSetBits(s_events, ENDED_BIT);
            result = ESP_FAIL;
        } else {
            s_frame_sent = true;
            s_last_frame_ms = client_ms;
            result = ESP_OK;
        }
    }
    xSemaphoreGive(s_lock);
    return result;
}

esp_err_t link_send_trigger_down(uint32_t timeout_ms)
{
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t result = ESP_ERR_INVALID_STATE;
    if (s_streaming && s_client != NULL) {
        /* Formatted under the same lock the frame send holds, so the frame
         * named is one this connection really sent. Before any frame, or
         * if the stamp will not format, the plain `down` fires in place. */
        char named[80];
        const char *text = BP_TRIGGER_DOWN_MESSAGE;
        if (s_frame_sent &&
            bp_format_trigger_down(named, sizeof named, s_last_frame_ms) > 0) {
            text = named;
        }
        int sent = esp_websocket_client_send_text(s_client, text, (int)strlen(text),
                                                  pdMS_TO_TICKS(timeout_ms));
        result = sent < 0 ? ESP_FAIL : ESP_OK;
    }
    xSemaphoreGive(s_lock);
    return result;
}

void link_service(void)
{
    portENTER_CRITICAL(&s_rtt_mux);
    bool pending = s_rtt_pending;
    double rtt = s_rtt_ms;
    s_rtt_pending = false;
    portEXIT_CRITICAL(&s_rtt_mux);

    char message[48];
    if (pending && bp_format_rtt(message, sizeof message, rtt) > 0) {
        link_send_text(message, CONFIG_BORESIGHT_SEND_TIMEOUT_MS);
    }
}

double link_rtt_ms(void)
{
    portENTER_CRITICAL(&s_rtt_mux);
    double rtt = s_rtt_ms;
    portEXIT_CRITICAL(&s_rtt_mux);
    return rtt;
}

/* --- Connection lifecycle ---------------------------------------------- */

static void run_session(esp_websocket_client_handle_t client)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_client = client;
    /* Hello before any frame, so the server's log names this device from
     * its first line about the session. */
    if (esp_websocket_client_send_text(client, s_hello, (int)strlen(s_hello),
                                       pdMS_TO_TICKS(HELLO_TIMEOUT_MS)) < 0) {
        ESP_LOGW(TAG, "hello was not sent");
    }
    s_session_id++;
    s_frame_sent = false;
    s_streaming = true;
    xSemaphoreGive(s_lock);

    ESP_LOGI(TAG, "connected; streaming");
    status_led_set_link(BP_LINK_STREAMING);
    /* Reaching the server proves a newly installed firmware works. */
    ota_mark_good();
    xEventGroupWaitBits(s_events, ENDED_BIT, pdFALSE, pdFALSE, portMAX_DELAY);

    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_streaming = false;
    s_client = NULL;
    xSemaphoreGive(s_lock);
    ESP_LOGW(TAG, "connection ended");
}

/* The socket URL for the next attempt. Built per attempt, not once, so a
 * server found by discovery can move between attempts. The token travels
 * as a query parameter, as the phone's does; setup mode admits only
 * URL-safe characters into it. */
static bool build_uri(const char *host, unsigned port)
{
    const char *token = settings()->token;
    int written;
    if (strlen(token) > 0) {
        written = snprintf(s_uri, sizeof s_uri, SCHEME "://%s:%u" FRAME_SOCKET_PATH
                                                       "?token=%s",
                           host, port, token);
    } else {
        written = snprintf(s_uri, sizeof s_uri, SCHEME "://%s:%u" FRAME_SOCKET_PATH,
                           host, port);
    }
    if (written < 0 || (size_t)written >= sizeof s_uri) {
        ESP_LOGE(TAG, "server address and token do not fit in the URI buffer");
        return false;
    }
    return true;
}

#if CONFIG_BORESIGHT_TLS
#define BUILT_WITH_TLS true
#else
#define BUILT_WITH_TLS false
#endif

typedef enum {
    DISCOVERY_FOUND = 0,
    DISCOVERY_NOT_FOUND,
    /* Found, but its TLS setting is not this build's: a configuration
     * error, not something more tries will fix. */
    DISCOVERY_TLS_MISMATCH,
} discovery_t;

#if CONFIG_BORESIGHT_EMULATOR
/* QEMU's user networking carries no multicast: the emulator build always
 * has an address configured (main.c refuses to start without one). */
static discovery_t discover(char *host, size_t size, unsigned *port)
{
    (void)host;
    (void)size;
    (void)port;
    return DISCOVERY_NOT_FOUND;
}
#else
#define DISCOVERY_TIMEOUT_MS 3000
#define DISCOVERY_MAX_RESULTS 4

static const char *txt_value(const mdns_result_t *result, const char *key)
{
    for (size_t i = 0; i < result->txt_count; i++) {
        if (strcmp(result->txt[i].key, key) == 0) {
            return result->txt[i].value != NULL ? result->txt[i].value : "";
        }
    }
    return NULL;
}

/* The first announced Boresight server with an IPv4 address. Every one
 * found is logged, so a second server on the network is no mystery. */
static discovery_t discover(char *host, size_t size, unsigned *port)
{
    static bool started;
    if (!started) {
        esp_err_t err = mdns_init();
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "mDNS did not start: %s", esp_err_to_name(err));
            return DISCOVERY_NOT_FOUND;
        }
        started = true;
    }
    ESP_LOGI(TAG, "no server address: looking for _boresight._tcp");
    mdns_result_t *results = NULL;
    if (mdns_query_ptr("_boresight", "_tcp", DISCOVERY_TIMEOUT_MS, DISCOVERY_MAX_RESULTS,
                       &results) != ESP_OK ||
        results == NULL) {
        ESP_LOGW(TAG, "no Boresight server announced on this network");
        return DISCOVERY_NOT_FOUND;
    }
    discovery_t outcome = DISCOVERY_NOT_FOUND;
    for (const mdns_result_t *r = results; r != NULL; r = r->next) {
        const mdns_ip_addr_t *address = r->addr;
        while (address != NULL && address->addr.type != ESP_IPADDR_TYPE_V4) {
            address = address->next;
        }
        if (address == NULL || r->port == 0) {
            continue;
        }
        char text[16];
        snprintf(text, sizeof text, IPSTR, IP2STR(&address->addr.u_addr.ip4));
        const char *tls = txt_value(r, "tls");
        ESP_LOGI(TAG, "found \"%s\" at %s:%u (tls %s)",
                 r->instance_name ? r->instance_name : "?", text, r->port,
                 tls ? tls : "not stated");
        if (outcome == DISCOVERY_FOUND) {
            continue; /* the first one wins; the rest are only logged */
        }
        if (!bp_discovery_tls_ok(tls, BUILT_WITH_TLS)) {
            if (BUILT_WITH_TLS) {
                ESP_LOGE(TAG,
                         "%s:%u does not announce TLS, and this build only "
                         "connects over TLS",
                         text, r->port);
            } else {
                ESP_LOGE(TAG,
                         "%s:%u requires TLS, and this build connects in plain "
                         "text: rebuild with TLS, or give the address of a "
                         "plain-text server",
                         text, r->port);
            }
            outcome = DISCOVERY_TLS_MISMATCH;
            continue;
        }
        strlcpy(host, text, size);
        *port = r->port;
        outcome = DISCOVERY_FOUND;
    }
    mdns_query_results_free(results);
    return outcome;
}
#endif

static void link_task(void *arg)
{
    (void)arg;
    uint32_t backoff_ms = 0;
    const esp_websocket_client_config_t config = {
        .uri = s_uri,
        .disable_auto_reconnect = true,
        .network_timeout_ms = 5000,
        .buffer_size = 2048,
        .task_prio = 6,
        .task_stack = 6144,
        /* A server that vanishes without closing is noticed in seconds, not
         * minutes. */
        .ping_interval_sec = 5,
        .pingpong_timeout_sec = 10,
#if CONFIG_BORESIGHT_TLS
        /* The only trust anchor. Hostname checking stays on. */
        .cert_pem = server_cert_pem_start,
#endif
    };

    for (;;) {
        if (!network_wait_connected(0)) {
            status_led_set_link(BP_LINK_JOINING_WIFI);
            network_wait_connected(portMAX_DELAY);
        }
        status_led_set_link(BP_LINK_CONNECTING);
        xEventGroupClearBits(s_events, CONNECTED_BIT | ENDED_BIT);
        s_failure = FAILURE_NONE;

        /* The configured address, or, when there is none, whichever
         * server is announced right now: found again every attempt, so a
         * server that moved is followed. */
        char discovered[16];
        const char *host = settings()->host;
        unsigned port = settings()->port;
        if (host[0] == '\0') {
            discovery_t found = discover(discovered, sizeof discovered, &port);
            if (found != DISCOVERY_FOUND) {
                uint32_t delay_ms;
                if (found == DISCOVERY_TLS_MISMATCH) {
                    status_led_set_link(BP_LINK_ERROR);
                    delay_ms = BP_BACKOFF_MAX_MS;
                } else {
                    backoff_ms = bp_backoff_next(backoff_ms);
                    delay_ms = backoff_ms;
                }
                vTaskDelay(pdMS_TO_TICKS(delay_ms));
                continue;
            }
            host = discovered;
        }
        /* A fresh client per attempt: simpler than reasoning about which
         * states a stopped client can be restarted from. */
        esp_websocket_client_handle_t client =
            build_uri(host, port) ? esp_websocket_client_init(&config) : NULL;
        if (client != NULL) {
            esp_websocket_register_events(client, WEBSOCKET_EVENT_ANY, on_event, NULL);
            ESP_LOGI(TAG, "connecting to " SCHEME "://%s:%u" FRAME_SOCKET_PATH, host,
                     port);
            EventBits_t bits = 0;
            if (esp_websocket_client_start(client) == ESP_OK) {
                bits = xEventGroupWaitBits(s_events, CONNECTED_BIT | ENDED_BIT, pdFALSE,
                                           pdFALSE, pdMS_TO_TICKS(CONNECT_TIMEOUT_MS));
            }
            if ((bits & CONNECTED_BIT) && !(bits & ENDED_BIT)) {
                run_session(client);
                backoff_ms = 0;
            }
            esp_websocket_client_stop(client);
            esp_websocket_client_destroy(client);
        } else {
            ESP_LOGE(TAG, "could not create the socket client");
        }

        uint32_t delay_ms;
        if (s_failure != FAILURE_NONE) {
            /* Retrying a refused token every second would only fill the
             * server's log; nothing changes until the device is set up
             * again. */
            status_led_set_link(BP_LINK_ERROR);
            delay_ms = BP_BACKOFF_MAX_MS;
        } else {
            backoff_ms = bp_backoff_next(backoff_ms);
            delay_ms = backoff_ms;
        }
        ESP_LOGI(TAG, "reconnecting in %" PRIu32 " ms", delay_ms);
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
}

#if CONFIG_BORESIGHT_TLS
/* The same figure the server prints under "sha256" at startup. */
static void log_certificate_fingerprint(void)
{
    mbedtls_x509_crt certificate;
    mbedtls_x509_crt_init(&certificate);
    int err = mbedtls_x509_crt_parse(&certificate,
                                     (const unsigned char *)server_cert_pem_start,
                                     strlen(server_cert_pem_start) + 1);
    if (err != 0) {
        ESP_LOGE(TAG, "main/server_cert.pem does not parse (-0x%04x)", -err);
    } else {
        unsigned char digest[32];
        mbedtls_sha256(certificate.raw.p, certificate.raw.len, digest, 0);
        char text[sizeof digest * 3];
        for (size_t i = 0; i < sizeof digest; i++) {
            snprintf(text + i * 3, 4, "%02X%s", digest[i],
                     i + 1 < sizeof digest ? ":" : "");
        }
        ESP_LOGI(TAG, "trusting only the server certificate with sha256 %s", text);
    }
    mbedtls_x509_crt_free(&certificate);
}
#endif

esp_err_t link_start(const char *version, int width, int height)
{
    s_events = xEventGroupCreate();
    s_lock = xSemaphoreCreateMutex();
    if (s_events == NULL || s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }

    if (bp_format_hello(s_hello, sizeof s_hello, version, width, height) < 0) {
        ESP_LOGE(TAG, "firmware version \"%s\" cannot go in a hello", version);
        return ESP_ERR_INVALID_ARG;
    }

#if CONFIG_BORESIGHT_TLS
    log_certificate_fingerprint();
#else
    ESP_LOGW(TAG, "TLS is off: the token crosses the network in plain text");
#endif

    /* Core 0, with the network stack it spends its time waiting on. */
    return xTaskCreatePinnedToCore(link_task, "link", 4096, NULL, 4, NULL, 0) == pdPASS
               ? ESP_OK
               : ESP_ERR_NO_MEM;
}
