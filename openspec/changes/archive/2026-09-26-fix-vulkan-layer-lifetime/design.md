## Context

See proposal.md for why. The layer (`native/vulkan_overlay/src/
overlay_layer.c`) keeps per-instance and per-device state in global
linked lists keyed off the loader's dispatch pointer. On
`vkCreateInstance` it starts a detached pthread that sleeps for
`BORESIGHT_OVERLAY_STARTUP_TIMEOUT_MS` (default 5000) and then reads
`instance_data_t::swapchain_seen`; `vkDestroyInstance` frees that
struct immediately. `swapchain_seen` is a `volatile int` written from
the application's thread in `vkCreateSwapchainKHR`. The `.bsov` reader
(`canvas_format.c`) validates magic, version and non-zero size only.

The `vulkan-present-overlay` capability is still defined only by the
unarchived `add-vulkan-present-overlay` change; `openspec/specs/` has
no `vulkan-present-overlay/` yet.

## Goals / Non-Goals

**Goals:**
- No access to freed instance state from any layer thread; no data
  race on the swapchain flag; `vkDestroyInstance` never blocks for the
  timeout.
- No NULL dereference on any host-allocation failure in the layer.
- `bsov_load` never hands the layer a rectangle outside the canvas and
  never allocates a size the file cannot back.
- Tests that exercise all of the above without needing a GPU, runnable
  under sanitizers.

**Non-Goals:**
- Changing the `.bsov` wire format, the environment variables, or any
  drawing behaviour for valid inputs.
- Defending against applications that violate Vulkan's own valid-usage
  rules in ways that are their bug (e.g. destroying an instance while a
  child device is still alive, or using a handle concurrently with its
  destruction). Those are listed under Risks rather than guessed at.
- A Vulkan-loader-driven CI test. A local probe run against lavapipe is
  done by hand (tasks.md) but not wired into `ctest`, since a loader +
  ICD is not something the test build can assume.

## Decisions

### Timeout thread: condition variable + join, factored into `startup_watchdog.{c,h}`
The thread waits with `pthread_cond_timedwait` on a condvar in a small
`startup_watchdog_t` embedded in `instance_data_t`, with
`CLOCK_MONOTONIC` set on the condvar (so wall-clock jumps can't shorten
or stretch the window). The wait loops on a `stop` flag to absorb
spurious wakeups. `vkDestroyInstance` sets `stop`, signals, and
`pthread_join`s before `free`. The thread only logs when it timed out
with neither `stop` nor `swapchain_seen` set. `swapchain_seen` is set
under the same mutex (`startup_watchdog_mark_swapchain_seen`) — the
cheapest correct option since it happens once per swapchain creation,
and it lets `seen` also wake the thread early so it exits as soon as
there is nothing left to report.

The timeout action is a callback (`on_timeout(timeout_ms)`) so the
watchdog is testable in isolation: the unit test counts callbacks and
heap-allocates/free()s the watchdog around each start/stop, so ASan
would flag exactly the original use-after-free if it came back.

Alternatives: keeping the detached thread but reference-counting
`instance_data_t` (thread drops the last reference) — fixes the UAF but
still leaves a sleeping thread per probe instance for 5 s and makes
teardown order harder to reason about; C11 atomics for the flag alone —
fixes the race but not the lifetime. Join is the simplest ownership
story: the instance owns the thread.

The log is emitted from the watchdog thread while *not* holding the
mutex, so a `vkDestroyInstance` racing a log line waits at most for one
`fprintf`, not for anything unbounded.

### `pthread_create` failure
If the thread can't be started, the instance still works; only the
diagnostic is lost (logged once). `startup_watchdog_stop` knows not to
join a thread that never started.

### Allocation failure policy
- `vkCreateInstance` / `vkCreateDevice`: the downstream object has
  already been created when our `calloc` runs, so we destroy it via the
  next layer's `vkDestroyInstance` / `vkDestroyDevice` and return
  `VK_ERROR_OUT_OF_HOST_MEMORY`. Alternative considered: return success
  and run as pure passthrough. Rejected because without our
  `instance_data_t` the layer's `vkGetInstanceProcAddr` cannot find the
  next layer's GIPA, so "passthrough" isn't actually possible for later
  calls — failing cleanly is the only safe option.
- `vkCreateDevice` also needs a non-NULL `instance_data_t` for its
  queue-family query; if `find_instance` misses (should not happen), the
  device is created with drawing disabled (`queue_supports_transfer =
  false`) instead of dereferencing NULL. Swapchain creation checks the
  same pointer.
- `vkCreateSwapchainKHR`: the swapchain is already created downstream,
  and failing now would break a working application over our own
  bookkeeping, so it returns the downstream result and simply isn't
  tracked (presents to an untracked swapchain already pass through).
  The same applies if the images array can't be allocated or
  `vkGetSwapchainImagesKHR` fails.
- Queue family properties array in `vkCreateDevice`: on failure, treat
  as "no transfer support" (drawing disabled for that device).

### Device teardown releases leftover swapchain state
`vkDestroyDevice` now tears down (after `vkDeviceWaitIdle`) any
swapchain state still registered, so the layer's own images, memory,
pool and semaphores are destroyed before the device. Destroying a
device with live swapchains is itself invalid usage by the application,
but leaking *our* children into a destroyed device would add a second
validation error the layer caused.

### Canvas validation limits
- `width`, `height` in `1..16384` — 16384 is the common
  `maxImageDimension2D` and above every real display; it also caps the
  grayscale allocation at 256 MiB and the layer's 4-byte expansion at
  1 GiB, so `pixel_count * 4` cannot overflow `size_t`.
- `rect_count <= 4096` — `render_overlay` produces tens of rectangles.
- Each rect: `w > 0`, `h > 0`, `x <= width - w`, `y <= height - h`
  (written as subtraction after checking `w <= width`, so no `x + w`
  overflow). This also guarantees `x`, `y`, `w`, `h` fit in `int32_t`
  for `VkOffset3D`.
- Before allocating, the file size (via `fseek`/`ftell`) must be at
  least header + rects + pixels. Trailing bytes are still tolerated, as
  before — rejecting them would be a behaviour change the writer never
  needed. Truncation was already rejected by `fread`; the size check
  only moves that rejection ahead of the allocation.

A rejected file returns nonzero from `bsov_load`; `try_setup_overlay`'s
existing "could not read a valid marker canvas" path handles it.

### Python reader mirrors the checks; writer unchanged
`canvas_format.unpack` gains the same checks (raising `ValueError`),
including a truncated-rectangles check (previously a `struct.error`).
`pack` is left permissive: existing tests use it to build deliberately
odd inputs, and the layer, not the writer, is the trust boundary. The
limits live as module constants next to the C `#define`s they mirror.

### Delta spec against an unarchived capability
The spec delta uses ADDED requirements only (no MODIFIED), and carries
the same `## Purpose` as `add-vulkan-present-overlay`'s spec. That makes
it archive correctly in either order: if that change archives first the
Purpose is ignored and the requirements are appended; if this one
archives first it creates the spec with a real Purpose and the other
change's ADDED requirements append to it.

### Tests
`BORESIGHT_OVERLAY_BUILD_TESTS` (default OFF) adds two executables and
`enable_testing()`: `test_canvas_format` (malformed/valid `.bsov`
files written to a temp dir) and `test_startup_watchdog` (fast
create/destroy churn, fires-once, suppressed-by-swapchain, stop after
fire). `BORESIGHT_OVERLAY_SANITIZE` (a string, e.g.
`address,undefined` or `thread`, default empty) adds
`-fsanitize=...` to the tests and the sources they compile. The shipped
layer build is unchanged unless a user opts in.

### Amendment: exported GetProcAddr self-references (found during verification)
The lavapipe probe (tasks.md 4.3) crashed with a stack overflow inside
`vkCreateInstance` — with the pre-change layer too, so not a
regression. Cause: the layer handed the loader `&vkGetInstanceProcAddr`
/ `&vkGetDeviceProcAddr`, i.e. the address of its own *exported*
symbols, which ELF interposition resolves to libvulkan's identically
named functions in any process that links the loader directly. The
loader then called itself as the layer, forever. Fixed by making the
implementations `static` (`boresight_GetInstanceProcAddr` /
`boresight_GetDeviceProcAddr`), exporting thin wrappers, and only ever
handing out the static addresses; the target is also built with hidden
default visibility so only the three `VK_LAYER_EXPORT` entry points are
exported. `vkcube` didn't show it; a plain program linked with
`-lvulkan` did, and so would any native Linux title that does the same.

## Risks / Trade-offs

- [An application destroys the `VkInstance` before its `VkDevice`] →
  `device_data_t::instance` then dangles. That is invalid usage
  (VUID-vkDestroyInstance-instance-00629) and every layer shares this
  assumption; not addressed here.
- [A handle is used on one thread while being destroyed on another] →
  `find_device`/`find_swapchain` return pointers after dropping the
  lock. Vulkan requires external synchronization for those handles, so
  this is the application's contract; not changed.
- [`vkDestroyInstance` can block for one `fprintf`] → only if it races
  the exact moment the timeout fires; bounded and harmless.
- [Canvas limits reject a legitimate >16384 px display] → no such
  swapchain can be created on current hardware; the limit is one
  constant on each side if it ever needs raising.
