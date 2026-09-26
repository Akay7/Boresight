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
#include "sdkconfig.h"

/* Milliseconds since boot, from the monotonic esp_timer clock. */
uint32_t boresight_now_ms(void);

void status_led_start(void);
void status_led_set_link(bp_link_state_t state);
/* Called per frame report from the server: did that frame solve? */
void status_led_report_stats(bool solved);

/* Wi-Fi on a board, QEMU's emulated Ethernet in an emulator build. Either
 * way, "connected" means an address has been assigned. */
esp_err_t network_start(void);
bool network_wait_connected(TickType_t timeout);

/* Starts the camera and reports the resolution actually applied. */
esp_err_t camera_start(int *width, int *height);

typedef struct {
    const uint8_t *data;
    size_t length;
    /* When the frame was captured, in milliseconds on the esp_timer clock:
     * what goes in the frame header. */
    double captured_ms;
    void *handle; /* the source's own, for camera_release */
} camera_frame_t;

/* The newest frame, or false if none is available right now. Every frame
 * grabbed must be released. */
bool camera_grab(camera_frame_t *frame);
void camera_release(camera_frame_t *frame);

/* Checked before anything starts: a button on a strapping pin can stop the
 * board booting at all, so it must be caught while the log is readable. */
bool buttons_valid(void);
esp_err_t buttons_start(void);

#if CONFIG_BORESIGHT_EMULATOR
/* Emulator only: sets a button's level in place of reading its pin. */
void buttons_inject(size_t index, bool pressed);
/* Emulator only: reads press, release and click from the console. */
void console_start(void);
#endif

esp_err_t link_start(const char *version, int width, int height);
bool link_is_streaming(void);
/* Changes every time a connection starts streaming, and is 0 before the
 * first. Lets a caller tell whether something it sent went out on the
 * connection that is open now. */
uint32_t link_session_id(void);
/* One binary message: 8-byte header, then the JPEG. ESP_ERR_TIMEOUT means
 * the frame was skipped without anything reaching the wire. */
esp_err_t link_send_frame(double client_ms, const uint8_t *jpeg, size_t length,
                          uint32_t timeout_ms);
esp_err_t link_send_text(const char *text, uint32_t timeout_ms);
/* The trigger's `down`, naming the last frame sent on this connection so
 * the server fires at that frame's aim; the plain `down` before any. */
esp_err_t link_send_trigger_down(uint32_t timeout_ms);
/* Sends anything the receive side queued (the round-trip report). Called
 * from the capture task, never from the socket's own event handler. */
void link_service(void);
double link_rtt_ms(void);
