#include "boresight_proto.h"

#include <stdio.h>
#include <string.h>

/* --- Frame header ------------------------------------------------------ */

void bp_pack_header(double client_ms, uint8_t out[BP_HEADER_SIZE])
{
    /* Shifted out explicitly rather than memcpy'd, so the bytes are
     * little-endian whatever the host is -- the host tests must prove
     * the same thing the board sends. */
    uint64_t bits;
    memcpy(&bits, &client_ms, sizeof bits);
    for (int i = 0; i < BP_HEADER_SIZE; i++) {
        out[i] = (uint8_t)(bits >> (8 * i));
    }
}

/* --- Control messages -------------------------------------------------- */

const char BP_TRIGGER_MESSAGE[] = "{\"type\":\"trigger\"}";
const char BP_TRIGGER_DOWN_MESSAGE[] = "{\"type\":\"trigger\",\"state\":\"down\"}";
const char BP_TRIGGER_UP_MESSAGE[] = "{\"type\":\"trigger\",\"state\":\"up\"}";

static int finish(int written, size_t size)
{
    return (written < 0 || (size_t)written >= size) ? -1 : written;
}

int bp_format_hello(char *out, size_t size, const char *version, int width,
                    int height)
{
    if (version == NULL || strpbrk(version, "\"\\") != NULL) {
        return -1;
    }
    int written;
    if (width > 0 && height > 0) {
        written = snprintf(out, size,
                           "{\"type\":\"hello\",\"client\":\"" BP_CLIENT_KIND
                           "\",\"version\":\"%s\",\"frame_size\":[%d,%d]}",
                           version, width, height);
    } else {
        written = snprintf(out, size,
                           "{\"type\":\"hello\",\"client\":\"" BP_CLIENT_KIND
                           "\",\"version\":\"%s\"}",
                           version);
    }
    return finish(written, size);
}

int bp_format_rtt(char *out, size_t size, double ms)
{
    return finish(snprintf(out, size, "{\"type\":\"rtt\",\"ms\":%.1f}", ms), size);
}

/* --- Button debouncing ------------------------------------------------- */

void bp_debounce_init(bp_debouncer_t *debouncer, uint32_t debounce_ms,
                      bool pressed_now, uint32_t now_ms)
{
    debouncer->debounce_ms = debounce_ms;
    debouncer->stable_pressed = pressed_now;
    debouncer->candidate_pressed = pressed_now;
    debouncer->candidate_since_ms = now_ms;
}

bp_button_event_t bp_debounce_update(bp_debouncer_t *debouncer, bool pressed,
                                     uint32_t now_ms)
{
    if (pressed != debouncer->candidate_pressed) {
        /* Any change restarts the clock: a bounce is a level that did
         * not last. */
        debouncer->candidate_pressed = pressed;
        debouncer->candidate_since_ms = now_ms;
        return BP_BUTTON_NONE;
    }
    if (debouncer->candidate_pressed == debouncer->stable_pressed) {
        return BP_BUTTON_NONE;
    }
    if ((uint32_t)(now_ms - debouncer->candidate_since_ms) < debouncer->debounce_ms) {
        return BP_BUTTON_NONE;
    }
    debouncer->stable_pressed = debouncer->candidate_pressed;
    return debouncer->stable_pressed ? BP_BUTTON_PRESSED : BP_BUTTON_RELEASED;
}

bool bp_debounce_settling(const bp_debouncer_t *debouncer)
{
    return debouncer->candidate_pressed != debouncer->stable_pressed;
}

/* --- Pins -------------------------------------------------------------- */

bool bp_button_gpio_allowed(int gpio)
{
    /* With the SD slot unused, 13 and 14 are the only pins that are not
     * the camera, PSRAM (16), UART (1, 3), the flash LED (4), the status
     * LED (33), or a boot strap (0, 2, 12, 15). */
    return gpio == 13 || gpio == 14;
}

/* --- Reconnect back-off ------------------------------------------------ */

uint32_t bp_backoff_next(uint32_t current_ms)
{
    if (current_ms < BP_BACKOFF_MIN_MS) {
        return BP_BACKOFF_MIN_MS;
    }
    if (current_ms >= BP_BACKOFF_MAX_MS / 2) {
        return BP_BACKOFF_MAX_MS;
    }
    return current_ms * 2;
}

/* --- Status LED -------------------------------------------------------- */

bp_led_pattern_t bp_led_pattern(bp_link_state_t state, bool last_solved,
                                uint32_t ms_since_stats)
{
    switch (state) {
    case BP_LINK_JOINING_WIFI:
        return BP_LED_SLOW_BLINK;
    case BP_LINK_CONNECTING:
        return BP_LED_FAST_BLINK;
    case BP_LINK_ERROR:
        return BP_LED_ERROR_FLASH;
    case BP_LINK_STREAMING:
    default:
        return (last_solved && ms_since_stats < BP_STATS_STALE_MS)
                   ? BP_LED_SOLID
                   : BP_LED_HEARTBEAT;
    }
}

bool bp_led_on(bp_led_pattern_t pattern, uint32_t now_ms)
{
    switch (pattern) {
    case BP_LED_SLOW_BLINK:
        return now_ms % 1000u < 500u;
    case BP_LED_FAST_BLINK:
        return now_ms % 250u < 125u;
    case BP_LED_ERROR_FLASH: {
        /* Three short flashes, then a pause: unlike any blink rate. */
        uint32_t phase = now_ms % 1500u;
        return phase < 500u && phase % 200u < 100u;
    }
    case BP_LED_SOLID:
        return true;
    case BP_LED_HEARTBEAT:
    default:
        return now_ms % 1000u < 80u;
    }
}

/* --- JPEG --------------------------------------------------------------- */

bool bp_jpeg_dimensions(const uint8_t *data, size_t length, int *width,
                        int *height)
{
    if (length < 4 || data[0] != 0xFF || data[1] != 0xD8) {
        return false;
    }
    size_t i = 2;
    while (i + 4 <= length) {
        if (data[i] != 0xFF) {
            return false;
        }
        uint8_t marker = data[i + 1];
        if (marker == 0xFF) { /* fill byte */
            i++;
            continue;
        }
        if (marker == 0xD9 || marker == 0xDA) {
            /* End of image, or scan data, before any frame header. */
            return false;
        }
        if (marker == 0x01 || (marker >= 0xD0 && marker <= 0xD7)) {
            i += 2; /* markers without a length */
            continue;
        }
        size_t segment = ((size_t)data[i + 2] << 8) | data[i + 3];
        if (segment < 2 || i + 2 + segment > length) {
            return false;
        }
        if (marker == 0xC0 || marker == 0xC1 || marker == 0xC2) {
            /* FF Cn, length, precision, height, width */
            if (segment < 7) {
                return false;
            }
            *height = (data[i + 5] << 8) | data[i + 6];
            *width = (data[i + 7] << 8) | data[i + 8];
            return *width > 0 && *height > 0;
        }
        i += 2 + segment;
    }
    return false;
}
