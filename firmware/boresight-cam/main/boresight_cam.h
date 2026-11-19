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
#include "boresight_setup.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"

/* CONFIG_BORESIGHT_EMULATOR as a value: Kconfig leaves an option that is
 * off undefined. */
#if CONFIG_BORESIGHT_EMULATOR
#define BORESIGHT_IS_EMULATOR true
#else
#define BORESIGHT_IS_EMULATOR false
#endif

/* Milliseconds since boot, from the monotonic esp_timer clock. */
uint32_t boresight_now_ms(void);

/* Restarts the device: esp_restart() on a board, a whole-system reset in
 * the emulator, where a CPU-only restart hangs. */
void boresight_restart(void) __attribute__((noreturn));

/* The settings in effect: the build's, with anything stored on the device
 * over them. Loaded once at boot, after NVS; read-only everywhere else. */
void settings_load(void);
const bp_settings_t *settings(void);
const bp_camera_limits_t *settings_camera_limits(void);
void settings_build_defaults(bp_settings_t *out);
/* Stores what differs from the build and forgets what does not. */
esp_err_t settings_save(const bp_settings_t *s);
/* Forgets everything stored: the build's values apply again. */
esp_err_t settings_erase(void);
/* Asks the next boot to enter setup mode, once (the emulator's `setup`). */
esp_err_t settings_request_setup(void);
bool settings_take_setup_request(void);

/* --- Firmware updates (ota.c) --------------------------------------------
 *
 * ota_boot_report logs the running firmware and slot, and a rolled-back
 * update. ota_mark_good keeps a newly installed firmware; call it once the
 * device has reached the server or setup mode. The upload calls run in
 * order: begin with the image's first bytes and its total size, write the
 * rest as it arrives, then finish (or abort). Each failure gives a reason
 * for the setup page.
 */
void ota_boot_report(void);
void ota_mark_good(void);
esp_err_t ota_upload_begin(const uint8_t *head, size_t length, size_t total,
                           const char **reason);
esp_err_t ota_upload_write(const void *data, size_t length);
esp_err_t ota_upload_finish(const char **reason);
void ota_upload_abort(void);
const char *ota_upload_version(void);

/* --- Setup mode ----------------------------------------------------------
 *
 * setup.c: whether this boot opens setup mode (a console request, no
 * network configured, or the trigger held 5 s from boot), and running it.
 * setup_run returns only if setup mode could not run or ran out on an
 * unconfigured device; the caller then stops where it is.
 */
bool setup_requested_at_boot(void);
void setup_run(void);
/* The page's handlers: a save or reset has been answered, restart soon. */
void setup_done(void);

/* setup_http.c: the page, at `home` for redirects. */
esp_err_t setup_http_start(const char *home);
void setup_http_stop(void);

/* setup_ap.c on a board, empty stand-ins in the emulator. */
#define SETUP_MAX_NETWORKS 16
size_t setup_networks(char names[][BP_SSID_MAX + 1], size_t max);
void setup_rescan(void);
#if !CONFIG_BORESIGHT_EMULATOR
/* The board's address on its own setup network, and the page there.
 * Public-looking, as WLED's is, not 192.168.4.1: an Android phone given a
 * private address for its sign-in check's public name never makes the
 * check, and says "no internet" instead of offering the page. The setup
 * network has no internet, so the address collides with nothing. */
#define SETUP_ADDRESS_BYTES 4, 3, 2, 1
#define SETUP_HOME "http://4.3.2.1/"

/* Opens the setup network; `name` gets its SSID. */
esp_err_t setup_network_start(char *name, size_t size);
void setup_network_stop(void);
#endif

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

/* Stops the camera, once the frame being sent is released, and starts it
 * again with the same settings. A long flash write -- erasing a sector --
 * must not run with the camera on: its interrupt stays live while flash
 * is unreadable, and esp32-camera's overflow warning there reads its
 * message from flash and crashes the board. No frame is grabbed while it
 * is paused. Both do nothing before camera_start(). */
void camera_pause(void);
void camera_resume(void);

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
