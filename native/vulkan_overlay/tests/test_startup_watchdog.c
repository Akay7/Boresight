/* The startup watchdog's lifetime contract, without a Vulkan loader.
 *
 * Each watchdog is heap-allocated and freed right after stop, exactly
 * as boresight_DestroyInstance frees its instance_data_t -- so under
 * -fsanitize=address a thread touching it after stop is reported as a
 * use-after-free, and under -fsanitize=thread any unsynchronized
 * access to its flags is reported as a race. */

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "startup_watchdog.h"

static atomic_int g_fired = 0;
static int g_failures = 0;

#define CHECK(cond, name)                                                  \
    do {                                                                   \
        if (!(cond)) {                                                     \
            fprintf(stderr, "FAIL: %s (%s:%d)\n", name, __FILE__, __LINE__); \
            g_failures++;                                                  \
        } else {                                                           \
            printf("ok: %s\n", name);                                      \
        }                                                                  \
    } while (0)

static void on_timeout(long timeout_ms) {
    (void)timeout_ms;
    atomic_fetch_add(&g_fired, 1);
}

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static void sleep_ms(long ms) {
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000L};
    nanosleep(&ts, NULL);
}

int main(void) {
    /* Probe-instance churn: many create->destroy pairs with the real
     * default timeout must neither wait it out nor fire. */
    atomic_store(&g_fired, 0);
    double start = now_ms();
    for (int i = 0; i < 500; i++) {
        startup_watchdog_t *w = malloc(sizeof(*w));
        startup_watchdog_start(w, 5000, on_timeout);
        if (i % 2) {
            startup_watchdog_mark_swapchain_seen(w);
        }
        startup_watchdog_stop(w);
        free(w);
    }
    double elapsed = now_ms() - start;
    printf("500 start/stop cycles took %.1f ms\n", elapsed);
    CHECK(elapsed < 2500.0, "stop does not wait out the timeout");
    CHECK(atomic_load(&g_fired) == 0, "stopped watchdogs never fire");

    /* No swapchain before the deadline: fires exactly once. */
    atomic_store(&g_fired, 0);
    {
        startup_watchdog_t *w = malloc(sizeof(*w));
        startup_watchdog_start(w, 30, on_timeout);
        sleep_ms(200);
        startup_watchdog_stop(w);
        free(w);
    }
    CHECK(atomic_load(&g_fired) == 1, "fires once when no swapchain is seen");

    /* A swapchain seen before the deadline suppresses it, and lets the
     * thread exit early (stop afterwards is then just a join). */
    atomic_store(&g_fired, 0);
    {
        startup_watchdog_t *w = malloc(sizeof(*w));
        startup_watchdog_start(w, 100, on_timeout);
        startup_watchdog_mark_swapchain_seen(w);
        sleep_ms(250);
        startup_watchdog_stop(w);
        free(w);
    }
    CHECK(atomic_load(&g_fired) == 0, "a seen swapchain suppresses the diagnostic");

    /* Marking seen after it already fired is harmless. */
    atomic_store(&g_fired, 0);
    {
        startup_watchdog_t *w = malloc(sizeof(*w));
        startup_watchdog_start(w, 10, on_timeout);
        sleep_ms(100);
        startup_watchdog_mark_swapchain_seen(w);
        startup_watchdog_stop(w);
        free(w);
    }
    CHECK(atomic_load(&g_fired) == 1, "late swapchain after firing is harmless");

    /* Racing stop against the deadline, many times: whichever wins, it
     * fires at most once per watchdog and nothing touches freed memory. */
    atomic_store(&g_fired, 0);
    for (int i = 0; i < 200; i++) {
        startup_watchdog_t *w = malloc(sizeof(*w));
        startup_watchdog_start(w, 1, on_timeout);
        if (i % 3 == 0) {
            sleep_ms(1);
        }
        startup_watchdog_stop(w);
        free(w);
    }
    CHECK(atomic_load(&g_fired) <= 200, "stop racing the deadline fires at most once each");

    if (g_failures) {
        fprintf(stderr, "%d failure(s)\n", g_failures);
        return 1;
    }
    return 0;
}
