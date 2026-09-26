/* The startup diagnostic's timer thread (spec: "An application that
 * cannot host this backend fails with an actionable diagnostic").
 *
 * Kept separate from overlay_layer.c so it can be unit-tested without a
 * Vulkan loader (tests/test_startup_watchdog.c), since its whole job is
 * a lifetime contract: the thread belongs to the watchdog that started
 * it, and `startup_watchdog_stop` wakes and joins it -- so the owning
 * VkInstance's state can be freed right after, without the thread ever
 * reading it again, and without vkDestroyInstance waiting out the
 * timeout. DXVK/Proton and many engines create and destroy a probe
 * VkInstance at startup, so "destroyed long before the timeout" is the
 * normal path, not an edge case. */

#ifndef BORESIGHT_STARTUP_WATCHDOG_H
#define BORESIGHT_STARTUP_WATCHDOG_H

#include <pthread.h>
#include <stdbool.h>

/* Called at most once, on the watchdog thread, with no lock held, if
 * `timeout_ms` elapses before either a swapchain is seen or the
 * watchdog is stopped. */
typedef void (*startup_watchdog_timeout_fn)(long timeout_ms);

typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t cond;
    bool stop;           /* guarded by `lock` */
    bool swapchain_seen; /* guarded by `lock` */

    bool running; /* thread was created and not yet joined; owner-thread only */
    pthread_t thread;
    long timeout_ms;
    startup_watchdog_timeout_fn on_timeout;
} startup_watchdog_t;

/* Parses BORESIGHT_OVERLAY_STARTUP_TIMEOUT_MS (positive milliseconds),
 * falling back to 5000 when unset or invalid. */
long startup_watchdog_timeout_from_env(void);

/* Initializes `w` and starts its thread. Returns 0 on success. On
 * failure `w` is still safe to pass to the other two functions (they
 * become no-ops beyond the flag bookkeeping) -- the caller only loses
 * the diagnostic, never the instance. */
int startup_watchdog_start(
    startup_watchdog_t *w, long timeout_ms, startup_watchdog_timeout_fn on_timeout
);

/* Records that a swapchain was created; suppresses the diagnostic and
 * lets the thread exit early. Callable from any thread. */
void startup_watchdog_mark_swapchain_seen(startup_watchdog_t *w);

/* Wakes the thread, joins it, and releases `w`'s sync objects. Returns
 * promptly regardless of the remaining timeout. Must be called exactly
 * once per `startup_watchdog_start`, before freeing `w`. */
void startup_watchdog_stop(startup_watchdog_t *w);

#endif /* BORESIGHT_STARTUP_WATCHDOG_H */
