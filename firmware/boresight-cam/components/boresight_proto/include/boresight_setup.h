/*
 * Setup mode's platform-independent half: the device's editable settings,
 * reading and checking what the setup page posts, escaping what it shows,
 * answering the setup network's name lookups, and checking a discovered
 * server's TLS setting against the build's.
 *
 * No ESP-IDF here either, so all of it is tested on the host
 * (../../test_host). The firmware supplies the defaults and the camera
 * limits from its build configuration; nothing here reads Kconfig.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Settings -----------------------------------------------------------*/

#define BP_SSID_MAX 32 /* bytes, as 802.11 allows */
#define BP_PASSWORD_MIN 8
#define BP_PASSWORD_MAX 63 /* a WPA2 passphrase; 64-hex PSKs are not taken */
#define BP_HOST_MAX 63
#define BP_TOKEN_MAX 128

typedef enum {
    BP_RES_VGA = 0, /* 640x480 */
    BP_RES_SVGA,    /* 800x600 */
    BP_RES_XGA,     /* 1024x768 */
    BP_RES_HD,      /* 1280x720 */
    BP_RES_COUNT,
} bp_resolution_t;

/* What the page posts and shows for each: "1024x768". */
const char *bp_resolution_name(bp_resolution_t resolution);
void bp_resolution_size(bp_resolution_t resolution, int *width, int *height);

typedef struct {
    char ssid[BP_SSID_MAX + 1];
    char password[BP_PASSWORD_MAX + 1];
    /* Empty: find the server through its announcement. */
    char host[BP_HOST_MAX + 1];
    uint16_t port;
    char token[BP_TOKEN_MAX + 1];
    bp_resolution_t resolution;
    int jpeg_quality;
    int max_fps;
    int exposure;
    int gain;
} bp_settings_t;

typedef struct {
    int min;
    int max;
} bp_range_t;

/* The camera settings' allowed ranges: the build configuration's own, so
 * the page cannot store a value menuconfig would refuse. */
typedef struct {
    bp_range_t jpeg_quality;
    bp_range_t max_fps;
    bp_range_t exposure;
    bp_range_t gain;
} bp_camera_limits_t;

/* --- Fields -------------------------------------------------------------*/

typedef enum {
    BP_FIELD_SSID = 0,
    BP_FIELD_PASSWORD,
    BP_FIELD_HOST,
    BP_FIELD_PORT,
    BP_FIELD_TOKEN,
    BP_FIELD_RESOLUTION,
    BP_FIELD_JPEG_QUALITY,
    BP_FIELD_MAX_FPS,
    BP_FIELD_EXPOSURE,
    BP_FIELD_GAIN,
    BP_FIELD_COUNT,
} bp_field_t;

/* The form field's name, as the page posts it: "ssid", "port", ... */
const char *bp_field_name(bp_field_t field);

/* Bit `1u << field` in a field set. */
typedef uint32_t bp_field_set_t;

/* --- Forms --------------------------------------------------------------
 *
 * application/x-www-form-urlencoded: `+` is a space, `%XX` a byte. Both
 * return the decoded length, or -1 when the input is malformed (a `%` not
 * followed by two hex digits) or the result, with its terminating NUL,
 * does not fit `size`. A decoded NUL byte is malformed too: it would
 * silently cut a C string short.
 */
int bp_form_decode(const char *in, size_t in_length, char *out, size_t size);

/* The decoded value of field `name` in `body`, or -1 if it is absent, and
 * -2 if it is present but malformed or too long for `size`. */
int bp_form_get(const char *body, const char *name, char *out, size_t size);

/*
 * Applies a posted form to `current`, writing the result to `out` only if
 * every field is valid; `*invalid` gets the set of fields that are not
 * (empty on success). Returns whether it succeeded.
 *
 * A field missing from the form keeps its current value, except the
 * network name, which a board cannot run without. The password and token
 * are write-only: posted empty, they keep the current value; they are
 * cleared only by `clear_password=1` or `clear_token=1`.
 */
bool bp_settings_apply_form(const bp_settings_t *current, const char *body,
                            const bp_camera_limits_t *limits, bp_settings_t *out,
                            bp_field_set_t *invalid);

/* --- Checks the page and the store share --------------------------------*/

bool bp_ssid_valid(const char *ssid);
/* Empty (an open network) or 8 to 63 printable ASCII characters. */
bool bp_password_valid(const char *password);
/* Empty, a dotted IPv4 address, or a host name of letters, digits and
 * hyphens in dot-separated labels. */
bool bp_host_valid(const char *host);
/* Empty, or URL-safe characters only (letters, digits, `-._~`): the token
 * travels unescaped in the socket URL's query string. */
bool bp_token_valid(const char *token);

/* --- HTML ---------------------------------------------------------------
 *
 * Escapes `&<>"'` so text can sit in an element or a quoted attribute.
 * Scanned network names come from anyone's access point. Returns the
 * escaped length, or -1 if it does not fit with its NUL.
 */
int bp_html_escape(const char *in, char *out, size_t size);

/* --- Setup network name lookups ----------------------------------------
 *
 * The reply to one DNS query on the setup network: an A query of class IN
 * is answered with `ip`, any other single-question query with no answer
 * (NOERROR, nothing found), so every name leads to the setup page.
 * Returns the reply's length, or -1 when the packet is to be ignored:
 * truncated, a response rather than a query, not a standard query, or
 * not exactly one question.
 */
int bp_dns_answer(const uint8_t *query, size_t length, const uint8_t ip[4],
                  uint8_t *out, size_t size);

/* --- Discovery ----------------------------------------------------------
 *
 * Whether a server announcing `tls` (its TXT value, NULL when absent) may
 * be used by a build with or without TLS. Absent counts as a mismatch:
 * the announcement does not say, and guessing would either leak the token
 * in plain text or fail the handshake for a reason nobody can see.
 */
bool bp_discovery_tls_ok(const char *tls, bool built_with_tls);

/* --- Firmware images ------------------------------------------------------
 *
 * What a firmware upload is, from its first bytes: an ESP-IDF application
 * image (the image header's magic), carrying an app descriptor at its
 * fixed place (offset 32, right after the image and first segment
 * headers), for this project, and for the same kind of target as the one
 * running -- an emulator image's version ends in "+emulator".
 */
#define BP_PROJECT_NAME "boresight-cam"
#define BP_EMULATOR_VERSION_SUFFIX "+emulator"
/* Enough of an image to check: through the descriptor's project name. */
#define BP_IMAGE_HEAD_SIZE 112

typedef enum {
    BP_IMAGE_OK = 0,
    BP_IMAGE_NOT_FIRMWARE,  /* not an ESP-IDF application image at all */
    BP_IMAGE_OTHER_PROJECT, /* an application, but not Boresight's camera */
    BP_IMAGE_WRONG_KIND,    /* an emulator image on a board, or the reverse */
} bp_image_check_t;

/* `version` gets the image's version (NUL-terminated, cut to fit) when the
 * head is long enough to hold one, whatever the verdict. */
bp_image_check_t bp_app_image_check(const uint8_t *head, size_t length,
                                    bool running_is_emulator, char *version,
                                    size_t version_size);

/* Why, in words for the setup page. */
const char *bp_image_check_reason(bp_image_check_t check, bool running_is_emulator);

#ifdef __cplusplus
}
#endif
