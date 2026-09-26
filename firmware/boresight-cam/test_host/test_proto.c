/*
 * Host tests for boresight_proto. A failing check prints its line and the
 * process exits non-zero, which is all CTest needs.
 */
#include "boresight_proto.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;

#define CHECK(condition)                                                    \
    do {                                                                    \
        if (!(condition)) {                                                 \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, \
                    #condition);                                            \
            failures++;                                                     \
        }                                                                   \
    } while (0)

/* --- Frame header ------------------------------------------------------ */

static void test_header_matches_the_server_codec(void)
{
    /* python -c "from boresight.stream import pack_frame;
     *            print(pack_frame(1234.5, b'').hex())"
     * -> 00000000004a9340 */
    const uint8_t expected[BP_HEADER_SIZE] = {0x00, 0x00, 0x00, 0x00,
                                              0x00, 0x4a, 0x93, 0x40};
    uint8_t header[BP_HEADER_SIZE];

    bp_pack_header(1234.5, header);

    CHECK(memcmp(header, expected, BP_HEADER_SIZE) == 0);
}

static void test_header_keeps_sub_millisecond_precision(void)
{
    /* python -c "from boresight.stream import pack_frame;
     *            print(pack_frame(86400000.125, b'').hex())"
     * -> 0000800070999441 */
    const uint8_t expected[BP_HEADER_SIZE] = {0x00, 0x00, 0x80, 0x00,
                                              0x70, 0x99, 0x94, 0x41};
    uint8_t header[BP_HEADER_SIZE];

    bp_pack_header(86400000.125, header);

    CHECK(memcmp(header, expected, BP_HEADER_SIZE) == 0);
}

/* --- Control messages -------------------------------------------------- */

static void test_hello_names_the_client_version_and_size(void)
{
    char buffer[128];

    int length = bp_format_hello(buffer, sizeof buffer, "0.1.0", 800, 600);

    CHECK(length > 0);
    CHECK(strcmp(buffer, "{\"type\":\"hello\",\"client\":\"esp32-cam\","
                         "\"version\":\"0.1.0\",\"frame_size\":[800,600]}") == 0);
}

static void test_hello_without_a_known_size_omits_it(void)
{
    char buffer[128];

    CHECK(bp_format_hello(buffer, sizeof buffer, "0.1.0", 0, 0) > 0);
    CHECK(strstr(buffer, "frame_size") == NULL);
}

static void test_hello_refuses_what_it_cannot_encode(void)
{
    char buffer[128];
    char tiny[16];

    CHECK(bp_format_hello(buffer, sizeof buffer, "bad\"version", 1, 1) == -1);
    CHECK(bp_format_hello(buffer, sizeof buffer, "bad\\version", 1, 1) == -1);
    CHECK(bp_format_hello(buffer, sizeof buffer, NULL, 1, 1) == -1);
    CHECK(bp_format_hello(tiny, sizeof tiny, "0.1.0", 800, 600) == -1);
}

static void test_rtt_and_trigger_messages(void)
{
    char buffer[64];

    CHECK(bp_format_rtt(buffer, sizeof buffer, 42.54) > 0);
    CHECK(strcmp(buffer, "{\"type\":\"rtt\",\"ms\":42.5}") == 0);
    CHECK(strcmp(BP_TRIGGER_MESSAGE, "{\"type\":\"trigger\"}") == 0);
    CHECK(strcmp(BP_TRIGGER_DOWN_MESSAGE, "{\"type\":\"trigger\",\"state\":\"down\"}") ==
          0);
    CHECK(strcmp(BP_TRIGGER_UP_MESSAGE, "{\"type\":\"trigger\",\"state\":\"up\"}") == 0);
}

/* --- Debouncer --------------------------------------------------------- */

typedef struct {
    uint32_t at_ms;
    bool pressed;
} sample_t;

static int count_events(const sample_t *samples, size_t count,
                        uint32_t sample_every_ms, uint32_t until_ms,
                        bp_button_event_t wanted)
{
    /* Feeds the level in effect at every tick, like the button task does
     * while settling. */
    bp_debouncer_t debouncer;
    bp_debounce_init(&debouncer, 10, false, 0);
    int events = 0;
    size_t next = 0;
    bool level = false;
    for (uint32_t now = 0; now <= until_ms; now += sample_every_ms) {
        while (next < count && samples[next].at_ms <= now) {
            level = samples[next].pressed;
            next++;
        }
        if (bp_debounce_update(&debouncer, level, now) == wanted) {
            events++;
        }
    }
    return events;
}

static int count_presses(const sample_t *samples, size_t count,
                         uint32_t sample_every_ms, uint32_t until_ms)
{
    return count_events(samples, count, sample_every_ms, until_ms, BP_BUTTON_PRESSED);
}

static int count_releases(const sample_t *samples, size_t count,
                          uint32_t sample_every_ms, uint32_t until_ms)
{
    return count_events(samples, count, sample_every_ms, until_ms, BP_BUTTON_RELEASED);
}

static void test_a_clean_press_is_one_event(void)
{
    const sample_t samples[] = {{100, true}, {300, false}};

    CHECK(count_presses(samples, 2, 1, 600) == 1);
}

static void test_bounce_on_both_edges_is_one_event(void)
{
    const sample_t samples[] = {
        {100, true}, {101, false}, {103, true}, {104, false}, {106, true},
        {300, false}, {301, true}, {302, false}, {305, true}, {306, false},
    };

    CHECK(count_presses(samples, sizeof samples / sizeof samples[0], 1, 600) == 1);
    CHECK(count_releases(samples, sizeof samples / sizeof samples[0], 1, 600) == 1);
}

static void test_a_long_hold_is_one_event(void)
{
    const sample_t samples[] = {{100, true}, {5100, false}};

    CHECK(count_presses(samples, 2, 1, 6000) == 1);
    CHECK(count_releases(samples, 2, 1, 6000) == 1);
}

static void test_the_release_comes_after_the_press_settles(void)
{
    /* Released at 5100, reported once it has read up for 10ms. */
    bp_debouncer_t debouncer;
    bp_debounce_init(&debouncer, 10, false, 0);
    CHECK(bp_debounce_update(&debouncer, true, 100) == BP_BUTTON_NONE);
    CHECK(bp_debounce_update(&debouncer, true, 110) == BP_BUTTON_PRESSED);
    CHECK(bp_debounce_update(&debouncer, false, 5100) == BP_BUTTON_NONE);
    CHECK(bp_debounce_update(&debouncer, false, 5109) == BP_BUTTON_NONE);
    CHECK(bp_debounce_update(&debouncer, false, 5110) == BP_BUTTON_RELEASED);
    CHECK(bp_debounce_update(&debouncer, false, 5200) == BP_BUTTON_NONE);
}

static void test_a_glitch_shorter_than_the_debounce_is_nothing(void)
{
    const sample_t samples[] = {{100, true}, {105, false}};

    CHECK(count_presses(samples, 2, 1, 600) == 0);
    CHECK(count_releases(samples, 2, 1, 600) == 0);
}

static void test_repeated_presses_each_count(void)
{
    sample_t samples[20];
    for (int i = 0; i < 10; i++) {
        samples[2 * i] = (sample_t){(uint32_t)(100 + i * 100), true};
        samples[2 * i + 1] = (sample_t){(uint32_t)(150 + i * 100), false};
    }

    CHECK(count_presses(samples, 20, 1, 1300) == 10);
    CHECK(count_releases(samples, 20, 1, 1300) == 10);
}

static void test_a_button_held_at_boot_does_not_fire(void)
{
    bp_debouncer_t debouncer;
    bp_debounce_init(&debouncer, 10, true, 0);

    for (uint32_t now = 0; now < 500; now++) {
        CHECK(bp_debounce_update(&debouncer, true, now) == BP_BUTTON_NONE);
    }
    CHECK(!bp_debounce_settling(&debouncer));
}

static void test_settling_reports_an_unconfirmed_change(void)
{
    bp_debouncer_t debouncer;
    bp_debounce_init(&debouncer, 10, false, 0);

    bp_debounce_update(&debouncer, true, 100);
    CHECK(bp_debounce_settling(&debouncer));
    CHECK(bp_debounce_update(&debouncer, true, 110) == BP_BUTTON_PRESSED);
    CHECK(!bp_debounce_settling(&debouncer));
}

static void test_the_clock_wrapping_does_not_fire_or_stall(void)
{
    bp_debouncer_t debouncer;
    uint32_t start = UINT32_MAX - 4;
    bp_debounce_init(&debouncer, 10, false, start);

    CHECK(bp_debounce_update(&debouncer, true, start) == BP_BUTTON_NONE);
    CHECK(bp_debounce_update(&debouncer, true, start + 5) == BP_BUTTON_NONE);
    CHECK(bp_debounce_update(&debouncer, true, start + 10) == BP_BUTTON_PRESSED);
}

/* --- Pins -------------------------------------------------------------- */

static void test_only_the_free_pins_take_a_button(void)
{
    CHECK(bp_button_gpio_allowed(13));
    CHECK(bp_button_gpio_allowed(14));

    const int reserved[] = {-1, 0, 1, 2, 3, 4, 12, 15, 16, 32, 33, 34, 39, 40};
    for (size_t i = 0; i < sizeof reserved / sizeof reserved[0]; i++) {
        CHECK(!bp_button_gpio_allowed(reserved[i]));
    }
}

/* --- Back-off ---------------------------------------------------------- */

static void test_backoff_doubles_up_to_the_cap(void)
{
    const uint32_t expected[] = {1000, 2000, 4000, 8000, 16000, 30000, 30000};
    uint32_t delay = 0;

    for (size_t i = 0; i < sizeof expected / sizeof expected[0]; i++) {
        delay = bp_backoff_next(delay);
        CHECK(delay == expected[i]);
    }
}

/* --- Status LED -------------------------------------------------------- */

static void test_led_patterns_follow_the_link_state(void)
{
    CHECK(bp_led_pattern(BP_LINK_JOINING_WIFI, true, 0) == BP_LED_SLOW_BLINK);
    CHECK(bp_led_pattern(BP_LINK_CONNECTING, true, 0) == BP_LED_FAST_BLINK);
    CHECK(bp_led_pattern(BP_LINK_ERROR, true, 0) == BP_LED_ERROR_FLASH);
    CHECK(bp_led_pattern(BP_LINK_STREAMING, true, 100) == BP_LED_SOLID);
    CHECK(bp_led_pattern(BP_LINK_STREAMING, false, 100) == BP_LED_HEARTBEAT);
}

static void test_stale_telemetry_is_not_shown_as_solved(void)
{
    CHECK(bp_led_pattern(BP_LINK_STREAMING, true, BP_STATS_STALE_MS) ==
          BP_LED_HEARTBEAT);
}

static void test_led_patterns_are_distinguishable(void)
{
    /* Sampled over 3 s at 10 ms: every pair of patterns must disagree
     * somewhere, or the person holding the gun cannot tell them apart. */
    const bp_led_pattern_t patterns[] = {BP_LED_SLOW_BLINK, BP_LED_FAST_BLINK,
                                         BP_LED_ERROR_FLASH, BP_LED_SOLID,
                                         BP_LED_HEARTBEAT};
    const size_t count = sizeof patterns / sizeof patterns[0];
    for (size_t a = 0; a < count; a++) {
        for (size_t b = a + 1; b < count; b++) {
            bool differ = false;
            for (uint32_t now = 0; now < 3000 && !differ; now += 10) {
                differ = bp_led_on(patterns[a], now) != bp_led_on(patterns[b], now);
            }
            CHECK(differ);
        }
    }
}

int main(void)
{
    test_header_matches_the_server_codec();
    test_header_keeps_sub_millisecond_precision();
    test_hello_names_the_client_version_and_size();
    test_hello_without_a_known_size_omits_it();
    test_hello_refuses_what_it_cannot_encode();
    test_rtt_and_trigger_messages();
    test_a_clean_press_is_one_event();
    test_bounce_on_both_edges_is_one_event();
    test_a_long_hold_is_one_event();
    test_a_glitch_shorter_than_the_debounce_is_nothing();
    test_the_release_comes_after_the_press_settles();
    test_repeated_presses_each_count();
    test_a_button_held_at_boot_does_not_fire();
    test_settling_reports_an_unconfirmed_change();
    test_the_clock_wrapping_does_not_fire_or_stall();
    test_only_the_free_pins_take_a_button();
    test_backoff_doubles_up_to_the_cap();
    test_led_patterns_follow_the_link_state();
    test_stale_telemetry_is_not_shown_as_solved();
    test_led_patterns_are_distinguishable();

    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("all boresight_proto checks passed\n");
    return 0;
}
