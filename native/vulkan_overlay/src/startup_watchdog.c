#include "startup_watchdog.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define DEFAULT_TIMEOUT_MS 5000L

long startup_watchdog_timeout_from_env(void) {
    long timeout_ms = DEFAULT_TIMEOUT_MS;
    const char *env = getenv("BORESIGHT_OVERLAY_STARTUP_TIMEOUT_MS");
    if (env && *env) {
        char *end = NULL;
        long parsed = strtol(env, &end, 10);
        if (end != env && parsed > 0) {
            timeout_ms = parsed;
        }
    }
    return timeout_ms;
}

static void *watchdog_thread(void *arg) {
    startup_watchdog_t *w = (startup_watchdog_t *)arg;

    /* Absolute deadline on CLOCK_MONOTONIC (the condvar is created with
     * that clock below), so a wall-clock jump neither cuts the window
     * short nor stretches it. */
    struct timespec deadline;
    clock_gettime(CLOCK_MONOTONIC, &deadline);
    deadline.tv_sec += w->timeout_ms / 1000;
    deadline.tv_nsec += (w->timeout_ms % 1000) * 1000000L;
    if (deadline.tv_nsec >= 1000000000L) {
        deadline.tv_sec += 1;
        deadline.tv_nsec -= 1000000000L;
    }

    bool fire = false;
    pthread_mutex_lock(&w->lock);
    /* Loop on the predicate, not the wait's return value: timedwait can
     * wake spuriously, and a signal can race the deadline. */
    while (!w->stop && !w->swapchain_seen) {
        if (pthread_cond_timedwait(&w->cond, &w->lock, &deadline) == ETIMEDOUT) {
            fire = !w->stop && !w->swapchain_seen;
            break;
        }
    }
    pthread_mutex_unlock(&w->lock);

    /* Logged without the lock held, so a concurrent stop waits at most
     * for this one call, never for anything unbounded. `w` itself stays
     * valid here: stop joins this thread before its owner frees it. */
    if (fire && w->on_timeout) {
        w->on_timeout(w->timeout_ms);
    }
    return NULL;
}

int startup_watchdog_start(
    startup_watchdog_t *w, long timeout_ms, startup_watchdog_timeout_fn on_timeout
) {
    memset(w, 0, sizeof(*w));
    w->timeout_ms = timeout_ms > 0 ? timeout_ms : DEFAULT_TIMEOUT_MS;
    w->on_timeout = on_timeout;

    pthread_mutex_init(&w->lock, NULL);

    pthread_condattr_t attr;
    pthread_condattr_init(&attr);
    pthread_condattr_setclock(&attr, CLOCK_MONOTONIC);
    pthread_cond_init(&w->cond, &attr);
    pthread_condattr_destroy(&attr);

    if (pthread_create(&w->thread, NULL, watchdog_thread, w) != 0) {
        return 1;
    }
    w->running = true;
    return 0;
}

void startup_watchdog_mark_swapchain_seen(startup_watchdog_t *w) {
    pthread_mutex_lock(&w->lock);
    w->swapchain_seen = true;
    pthread_cond_signal(&w->cond);
    pthread_mutex_unlock(&w->lock);
}

void startup_watchdog_stop(startup_watchdog_t *w) {
    pthread_mutex_lock(&w->lock);
    w->stop = true;
    pthread_cond_signal(&w->cond);
    pthread_mutex_unlock(&w->lock);

    if (w->running) {
        pthread_join(w->thread, NULL);
        w->running = false;
    }
    pthread_cond_destroy(&w->cond);
    pthread_mutex_destroy(&w->lock);
}
