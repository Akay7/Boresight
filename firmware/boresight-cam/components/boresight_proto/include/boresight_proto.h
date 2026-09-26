/*
 * Platform-independent pieces of the Boresight ESP32-CAM firmware.
 *
 * Nothing here includes ESP-IDF, so it builds and runs on the host
 * (see ../../test_host). What goes on the wire, when a button counts as
 * pressed, which pins a button may use and what the LED shows are all
 * decided here, where a test can reach them without a board.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Frame header -------------------------------------------------------
 *
 * One binary WebSocket message per frame: this 8-byte header, then the
 * JPEG. The header is a little-endian IEEE-754 double of milliseconds
 * from the device's own monotonic clock -- byte for byte what
 * `boresight.stream.pack_frame` writes, so the server cannot tell a
 * device frame from a phone frame.
 */
#define BP_HEADER_SIZE 8

void bp_pack_header(double client_ms, uint8_t out[BP_HEADER_SIZE]);

/* The server times aim smoothing by the interval between two frames'
 * stamps, so a frame is stamped when it was captured, not when it was
 * sent. `driver_ms` is the camera driver's capture time and `now_ms` the
 * same clock now, both in milliseconds; the driver's time is used when it
 * is plausible -- positive, not in the future, and no more than
 * BP_CAPTURE_MAX_AGE_MS old -- and `now_ms` otherwise, so a driver that
 * does not stamp its frames, or stamps them from another clock, degrades
 * to stamping at grab rather than to nonsense. */
#define BP_CAPTURE_MAX_AGE_MS 1000.0

double bp_capture_ms(double driver_ms, double now_ms);

/* --- Control messages ---------------------------------------------------
 *
 * JSON text messages on the same socket. Each formatter returns the
 * length written, or -1 if it did not fit or an input would need
 * escaping (nothing here escapes, so nothing here accepts a quote).
 */
#define BP_CLIENT_KIND "esp32-cam"

/* A plain trigger is one click. Down and up hold the button between them,
 * which is what this firmware sends; the plain form is kept for the
 * wire-format test and older servers' documentation. */
extern const char BP_TRIGGER_MESSAGE[];
extern const char BP_TRIGGER_DOWN_MESSAGE[];
extern const char BP_TRIGGER_UP_MESSAGE[];

int bp_format_hello(char *out, size_t size, const char *version, int width,
                    int height);
int bp_format_rtt(char *out, size_t size, double ms);

/* --- JPEG ----------------------------------------------------------------
 *
 * Pixel size from the first baseline, extended or progressive frame header.
 * False if the data is not a JPEG or ends before one. */
bool bp_jpeg_dimensions(const uint8_t *data, size_t length, int *width,
                        int *height);

/* --- Button debouncing --------------------------------------------------
 *
 * Integrating debouncer: the input must read the same level for
 * `debounce_ms` before it is believed. Each debounced transition is one
 * event -- pressed or released; hold and bounce are not events.
 */
typedef enum {
    BP_BUTTON_NONE = 0,
    BP_BUTTON_PRESSED,
    BP_BUTTON_RELEASED,
} bp_button_event_t;

typedef struct {
    uint32_t debounce_ms;
    bool stable_pressed;
    bool candidate_pressed;
    uint32_t candidate_since_ms;
} bp_debouncer_t;

/* `pressed_now` seeds the stable state, so a button held at boot does not
 * fire until it has been released and pressed again. Its release is still
 * reported; the caller ignores a release it never saw pressed. */
void bp_debounce_init(bp_debouncer_t *debouncer, uint32_t debounce_ms,
                      bool pressed_now, uint32_t now_ms);

bp_button_event_t bp_debounce_update(bp_debouncer_t *debouncer, bool pressed,
                                     uint32_t now_ms);

/* True while the input disagrees with the stable state, i.e. the caller
 * must keep sampling until it settles one way or the other. */
bool bp_debounce_settling(const bp_debouncer_t *debouncer);

/* --- Pins ---------------------------------------------------------------
 *
 * AI-Thinker ESP32-CAM. An allowlist rather than a denylist: almost every
 * pin is taken by the camera, PSRAM, the serial console, the flash LED or
 * a boot strap, and a pin forgotten from a denylist fails at boot in ways
 * that look like a broken board (GPIO12 high selects 1.8 V flash).
 */
bool bp_button_gpio_allowed(int gpio);

/* --- Reconnect back-off -------------------------------------------------*/
#define BP_BACKOFF_MIN_MS 1000u
#define BP_BACKOFF_MAX_MS 30000u

/* Next delay after a failed attempt waited `current_ms`; 0 starts over. */
uint32_t bp_backoff_next(uint32_t current_ms);

/* --- Status LED ---------------------------------------------------------*/
typedef enum {
    BP_LINK_JOINING_WIFI = 0,
    BP_LINK_CONNECTING,
    BP_LINK_ERROR,
    BP_LINK_STREAMING,
} bp_link_state_t;

typedef enum {
    BP_LED_SLOW_BLINK = 0, /* joining Wi-Fi */
    BP_LED_FAST_BLINK,     /* connecting to the server */
    BP_LED_ERROR_FLASH,    /* configuration, token or certificate error */
    BP_LED_SOLID,          /* streaming, last frame solved */
    BP_LED_HEARTBEAT,      /* streaming, last frame not solved */
} bp_led_pattern_t;

/* Telemetry older than this counts as unsolved, so a stalled server does
 * not leave the LED claiming the markers are in view. */
#define BP_STATS_STALE_MS 1000u

bp_led_pattern_t bp_led_pattern(bp_link_state_t state, bool last_solved,
                                uint32_t ms_since_stats);

bool bp_led_on(bp_led_pattern_t pattern, uint32_t now_ms);

#ifdef __cplusplus
}
#endif
