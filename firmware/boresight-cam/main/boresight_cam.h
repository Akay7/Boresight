/*
 * The firmware's modules, as main.c wires them together.
 *
 *   status_led  what the person holding the gun can see
 *   wifi        station mode, reconnect with back-off
 *   camera      OV2640 with exposure and gain pinned
 *   link        the frame socket: connect, hello, send, telemetry
 *   buttons     debounced push buttons and their actions
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "boresight_proto.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"

/* Milliseconds since boot, from the monotonic esp_timer clock. */
uint32_t boresight_now_ms(void);

void status_led_start(void);
void status_led_set_link(bp_link_state_t state);
/* Called per frame report from the server: did that frame solve? */
void status_led_report_stats(bool solved);

esp_err_t wifi_start(void);
bool wifi_wait_connected(TickType_t timeout);

/* Starts the camera and reports the resolution actually applied. */
esp_err_t camera_start(int *width, int *height);

/* Checked before anything starts: a button on a strapping pin can stop the
 * board booting at all, so it must be caught while the log is readable. */
bool buttons_valid(void);
esp_err_t buttons_start(void);

esp_err_t link_start(const char *version, int width, int height);
bool link_is_streaming(void);
/* One binary message: 8-byte header, then the JPEG. ESP_ERR_TIMEOUT means
 * the frame was skipped without anything reaching the wire. */
esp_err_t link_send_frame(double client_ms, const uint8_t *jpeg, size_t length,
                          uint32_t timeout_ms);
esp_err_t link_send_text(const char *text, uint32_t timeout_ms);
/* Sends anything the receive side queued (the round-trip report). Called
 * from the capture task, never from the socket's own event handler. */
void link_service(void);
double link_rtt_ms(void);
