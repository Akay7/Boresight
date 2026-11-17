#include "boresight_setup.h"

#include <string.h>

/* --- Settings ----------------------------------------------------------- */

static const struct {
    const char *name;
    int width;
    int height;
} RESOLUTIONS[BP_RES_COUNT] = {
    [BP_RES_VGA] = {"640x480", 640, 480},
    [BP_RES_SVGA] = {"800x600", 800, 600},
    [BP_RES_XGA] = {"1024x768", 1024, 768},
    [BP_RES_HD] = {"1280x720", 1280, 720},
};

const char *bp_resolution_name(bp_resolution_t resolution)
{
    return resolution < BP_RES_COUNT ? RESOLUTIONS[resolution].name : "";
}

void bp_resolution_size(bp_resolution_t resolution, int *width, int *height)
{
    if (resolution >= BP_RES_COUNT) {
        resolution = BP_RES_XGA;
    }
    *width = RESOLUTIONS[resolution].width;
    *height = RESOLUTIONS[resolution].height;
}

static const char *const FIELD_NAMES[BP_FIELD_COUNT] = {
    [BP_FIELD_SSID] = "ssid",
    [BP_FIELD_PASSWORD] = "password",
    [BP_FIELD_HOST] = "host",
    [BP_FIELD_PORT] = "port",
    [BP_FIELD_TOKEN] = "token",
    [BP_FIELD_RESOLUTION] = "resolution",
    [BP_FIELD_JPEG_QUALITY] = "jpeg_quality",
    [BP_FIELD_MAX_FPS] = "max_fps",
    [BP_FIELD_EXPOSURE] = "exposure",
    [BP_FIELD_GAIN] = "gain",
};

const char *bp_field_name(bp_field_t field)
{
    return field < BP_FIELD_COUNT ? FIELD_NAMES[field] : "";
}

/* --- Forms -------------------------------------------------------------- */

static int hex_value(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    return -1;
}

int bp_form_decode(const char *in, size_t in_length, char *out, size_t size)
{
    size_t written = 0;
    for (size_t i = 0; i < in_length; i++) {
        char c = in[i];
        if (c == '+') {
            c = ' ';
        } else if (c == '%') {
            if (i + 2 >= in_length) {
                return -1; /* fewer than two characters follow */
            }
            int high = hex_value(in[i + 1]);
            int low = hex_value(in[i + 2]);
            if (high < 0 || low < 0) {
                return -1;
            }
            c = (char)(high * 16 + low);
            i += 2;
        }
        if (c == '\0' || written + 1 >= size) {
            return -1;
        }
        out[written++] = c;
    }
    if (size == 0) {
        return -1;
    }
    out[written] = '\0';
    return (int)written;
}

int bp_form_get(const char *body, const char *name, char *out, size_t size)
{
    const size_t name_length = strlen(name);
    const char *pair = body;
    while (pair != NULL && *pair != '\0') {
        const char *end = strchr(pair, '&');
        const size_t pair_length = end != NULL ? (size_t)(end - pair) : strlen(pair);
        const char *equals = memchr(pair, '=', pair_length);
        const size_t key_length = equals != NULL ? (size_t)(equals - pair) : pair_length;
        if (key_length == name_length && memcmp(pair, name, name_length) == 0) {
            const char *value = equals != NULL ? equals + 1 : pair + pair_length;
            const size_t value_length = (size_t)(pair + pair_length - value);
            int length = bp_form_decode(value, value_length, out, size);
            return length < 0 ? -2 : length;
        }
        pair = end != NULL ? end + 1 : NULL;
    }
    return -1;
}

/* --- Checks --------------------------------------------------------------*/

bool bp_ssid_valid(const char *ssid)
{
    const size_t length = strlen(ssid);
    if (length == 0 || length > BP_SSID_MAX) {
        return false;
    }
    for (size_t i = 0; i < length; i++) {
        const unsigned char c = (unsigned char)ssid[i];
        if (c < 0x20 || c == 0x7f) {
            return false;
        }
    }
    return true;
}

bool bp_password_valid(const char *password)
{
    const size_t length = strlen(password);
    if (length == 0) {
        return true;
    }
    if (length < BP_PASSWORD_MIN || length > BP_PASSWORD_MAX) {
        return false;
    }
    for (size_t i = 0; i < length; i++) {
        const unsigned char c = (unsigned char)password[i];
        if (c < 0x20 || c > 0x7e) {
            return false;
        }
    }
    return true;
}

static bool is_digit(char c)
{
    return c >= '0' && c <= '9';
}

static bool is_alnum(char c)
{
    return is_digit(c) || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

static bool ipv4_valid(const char *host)
{
    int parts = 0;
    const char *p = host;
    for (;;) {
        int value = 0;
        int digits = 0;
        while (is_digit(*p)) {
            value = value * 10 + (*p - '0');
            digits++;
            p++;
        }
        if (digits == 0 || digits > 3 || value > 255) {
            return false;
        }
        parts++;
        if (*p == '\0') {
            return parts == 4;
        }
        if (*p != '.' || parts == 4) {
            return false;
        }
        p++;
    }
}

bool bp_host_valid(const char *host)
{
    const size_t length = strlen(host);
    if (length == 0) {
        return true;
    }
    if (length > BP_HOST_MAX) {
        return false;
    }
    /* Digits and dots only is meant as an address, and must be one: a
     * mistyped "192.168.1" is an error, not a host name. */
    bool numeric = true;
    for (size_t i = 0; i < length; i++) {
        if (!is_digit(host[i]) && host[i] != '.') {
            numeric = false;
            break;
        }
    }
    if (numeric) {
        return ipv4_valid(host);
    }
    size_t label = 0;
    for (size_t i = 0; i <= length; i++) {
        const char c = host[i];
        if (c == '.' || c == '\0') {
            if (label == 0 || host[i - 1] == '-') {
                return false;
            }
            label = 0;
            continue;
        }
        if (!is_alnum(c) && c != '-') {
            return false;
        }
        if (label == 0 && c == '-') {
            return false;
        }
        label++;
    }
    return true;
}

bool bp_token_valid(const char *token)
{
    const size_t length = strlen(token);
    if (length > BP_TOKEN_MAX) {
        return false;
    }
    for (size_t i = 0; i < length; i++) {
        const char c = token[i];
        if (!is_alnum(c) && c != '-' && c != '.' && c != '_' && c != '~') {
            return false;
        }
    }
    return true;
}

/* --- Applying a form ---------------------------------------------------- */

/* A whole decimal number, no sign, within [min, max]. */
static bool parse_in_range(const char *text, int min, int max, int *value)
{
    const size_t length = strlen(text);
    if (length == 0 || length > 9) {
        return false;
    }
    long result = 0;
    for (size_t i = 0; i < length; i++) {
        if (!is_digit(text[i])) {
            return false;
        }
        result = result * 10 + (text[i] - '0');
    }
    if (result < min || result > max) {
        return false;
    }
    *value = (int)result;
    return true;
}

static bool checked(const char *body, const char *name)
{
    char value[8];
    if (bp_form_get(body, name, value, sizeof value) < 0) {
        return false;
    }
    return strcmp(value, "1") == 0 || strcmp(value, "on") == 0;
}

/* A write-only secret: a new value replaces it, an empty one keeps it, and
 * only the clear box removes it. */
static bool apply_secret(const char *body, bp_field_t field, const char *clear_name,
                         bool (*valid)(const char *), char *stored, size_t size)
{
    char value[BP_TOKEN_MAX + 1];
    const size_t capacity = size < sizeof value ? size : sizeof value;
    const int length = bp_form_get(body, bp_field_name(field), value, capacity);
    if (length == -2) {
        return false;
    }
    if (length > 0) {
        if (!valid(value)) {
            return false;
        }
        memcpy(stored, value, (size_t)length + 1);
    } else if (checked(body, clear_name)) {
        stored[0] = '\0';
    }
    return true;
}

static bool apply_number(const char *body, bp_field_t field, bp_range_t range,
                         int *stored)
{
    char value[16];
    const int length = bp_form_get(body, bp_field_name(field), value, sizeof value);
    if (length == -1) {
        return true; /* not posted: keep */
    }
    return length >= 0 && parse_in_range(value, range.min, range.max, stored);
}

bool bp_settings_apply_form(const bp_settings_t *current, const char *body,
                            const bp_camera_limits_t *limits, bp_settings_t *out,
                            bp_field_set_t *invalid)
{
    bp_settings_t next = *current;
    bp_field_set_t bad = 0;
    char value[BP_HOST_MAX + 1];
    int length;

    /* Required: a board without a network name cannot run at all. */
    length = bp_form_get(body, bp_field_name(BP_FIELD_SSID), next.ssid, sizeof next.ssid);
    if (length < 0 || !bp_ssid_valid(next.ssid)) {
        bad |= 1u << BP_FIELD_SSID;
    }

    if (!apply_secret(body, BP_FIELD_PASSWORD, "clear_password", bp_password_valid,
                      next.password, sizeof next.password)) {
        bad |= 1u << BP_FIELD_PASSWORD;
    }
    if (!apply_secret(body, BP_FIELD_TOKEN, "clear_token", bp_token_valid, next.token,
                      sizeof next.token)) {
        bad |= 1u << BP_FIELD_TOKEN;
    }

    length = bp_form_get(body, bp_field_name(BP_FIELD_HOST), value, sizeof value);
    if (length == -2 || (length >= 0 && !bp_host_valid(value))) {
        bad |= 1u << BP_FIELD_HOST;
    } else if (length >= 0) {
        memcpy(next.host, value, (size_t)length + 1);
    }

    int port = next.port;
    if (!apply_number(body, BP_FIELD_PORT, (bp_range_t){1, 65535}, &port)) {
        bad |= 1u << BP_FIELD_PORT;
    }
    next.port = (uint16_t)port;

    length = bp_form_get(body, bp_field_name(BP_FIELD_RESOLUTION), value, sizeof value);
    if (length == -2) {
        bad |= 1u << BP_FIELD_RESOLUTION;
    } else if (length >= 0) {
        bool known = false;
        for (int r = 0; r < BP_RES_COUNT; r++) {
            if (strcmp(value, RESOLUTIONS[r].name) == 0) {
                next.resolution = (bp_resolution_t)r;
                known = true;
            }
        }
        if (!known) {
            bad |= 1u << BP_FIELD_RESOLUTION;
        }
    }

    if (!apply_number(body, BP_FIELD_JPEG_QUALITY, limits->jpeg_quality,
                      &next.jpeg_quality)) {
        bad |= 1u << BP_FIELD_JPEG_QUALITY;
    }
    if (!apply_number(body, BP_FIELD_MAX_FPS, limits->max_fps, &next.max_fps)) {
        bad |= 1u << BP_FIELD_MAX_FPS;
    }
    if (!apply_number(body, BP_FIELD_EXPOSURE, limits->exposure, &next.exposure)) {
        bad |= 1u << BP_FIELD_EXPOSURE;
    }
    if (!apply_number(body, BP_FIELD_GAIN, limits->gain, &next.gain)) {
        bad |= 1u << BP_FIELD_GAIN;
    }

    *invalid = bad;
    if (bad != 0) {
        return false;
    }
    *out = next;
    return true;
}

/* --- HTML --------------------------------------------------------------- */

int bp_html_escape(const char *in, char *out, size_t size)
{
    size_t written = 0;
    for (const char *p = in; *p != '\0'; p++) {
        const char *replacement = NULL;
        switch (*p) {
        case '&':
            replacement = "&amp;";
            break;
        case '<':
            replacement = "&lt;";
            break;
        case '>':
            replacement = "&gt;";
            break;
        case '"':
            replacement = "&quot;";
            break;
        case '\'':
            replacement = "&#39;";
            break;
        default:
            break;
        }
        const size_t length = replacement != NULL ? strlen(replacement) : 1;
        if (written + length + 1 > size) {
            return -1;
        }
        if (replacement != NULL) {
            memcpy(out + written, replacement, length);
        } else {
            out[written] = *p;
        }
        written += length;
    }
    if (size == 0) {
        return -1;
    }
    out[written] = '\0';
    return (int)written;
}

/* --- DNS ---------------------------------------------------------------- */

#define DNS_HEADER 12
#define DNS_TYPE_A 1
#define DNS_CLASS_IN 1
#define DNS_TTL_S 60

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((p[0] << 8) | p[1]);
}

static void write16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value >> 8);
    p[1] = (uint8_t)value;
}

int bp_dns_answer(const uint8_t *query, size_t length, const uint8_t ip[4],
                  uint8_t *out, size_t size)
{
    if (length < DNS_HEADER) {
        return -1;
    }
    const bool is_response = (query[2] & 0x80) != 0;
    const unsigned opcode = (query[2] >> 3) & 0x0F;
    if (is_response || opcode != 0 || read16(query + 4) != 1) {
        return -1;
    }

    /* The one question: a name in plain labels (a query has nothing to
     * point back to), then its type and class. */
    size_t at = DNS_HEADER;
    for (;;) {
        if (at >= length) {
            return -1;
        }
        const uint8_t label = query[at];
        if (label == 0) {
            at++;
            break;
        }
        if (label > 63) {
            return -1;
        }
        at += 1u + label;
    }
    if (at + 4 > length) {
        return -1;
    }
    const uint16_t qtype = read16(query + at);
    const uint16_t qclass = read16(query + at + 2);
    const size_t question_end = at + 4;

    const bool answer = qtype == DNS_TYPE_A && qclass == DNS_CLASS_IN;
    const size_t reply_length = question_end + (answer ? 16u : 0u);
    if (reply_length > size) {
        return -1;
    }

    /* The header and the question as asked; any additional records (an
     * EDNS option) are left out of the reply. */
    memcpy(out, query, question_end);
    out[2] = (uint8_t)(0x80 | 0x04 | (query[2] & 0x01)); /* QR, AA, RD as asked */
    out[3] = 0x00;                                       /* no RA, NOERROR */
    write16(out + 6, answer ? 1 : 0);
    write16(out + 8, 0);
    write16(out + 10, 0);

    if (answer) {
        uint8_t *a = out + question_end;
        a[0] = 0xC0; /* the name: a pointer to the question's, at 12 */
        a[1] = DNS_HEADER;
        write16(a + 2, DNS_TYPE_A);
        write16(a + 4, DNS_CLASS_IN);
        a[6] = 0;
        a[7] = 0;
        write16(a + 8, DNS_TTL_S);
        write16(a + 10, 4);
        memcpy(a + 12, ip, 4);
    }
    return (int)reply_length;
}

/* --- Discovery ---------------------------------------------------------- */

bool bp_discovery_tls_ok(const char *tls, bool built_with_tls)
{
    if (tls == NULL) {
        return false;
    }
    if (strcmp(tls, "1") == 0) {
        return built_with_tls;
    }
    if (strcmp(tls, "0") == 0) {
        return !built_with_tls;
    }
    return false;
}

/* --- Firmware images ---------------------------------------------------- */

#define IMAGE_MAGIC 0xE9
#define APP_DESC_OFFSET 32
#define APP_DESC_MAGIC 0xABCD5432u
#define APP_DESC_VERSION (APP_DESC_OFFSET + 16)
#define APP_DESC_PROJECT (APP_DESC_OFFSET + 48)
#define APP_DESC_FIELD 32

/* A fixed-size, possibly unterminated descriptor string, as a C string. */
static void field(const uint8_t *at, char *out, size_t size)
{
    size_t length = 0;
    while (length < APP_DESC_FIELD && at[length] != 0) {
        length++;
    }
    if (size == 0) {
        return;
    }
    if (length >= size) {
        length = size - 1;
    }
    memcpy(out, at, length);
    out[length] = '\0';
}

static bool ends_with(const char *text, const char *suffix)
{
    const size_t a = strlen(text);
    const size_t b = strlen(suffix);
    return a >= b && strcmp(text + a - b, suffix) == 0;
}

bp_image_check_t bp_app_image_check(const uint8_t *head, size_t length,
                                    bool running_is_emulator, char *version,
                                    size_t version_size)
{
    if (version != NULL && version_size > 0) {
        version[0] = '\0';
    }
    if (length < BP_IMAGE_HEAD_SIZE || head[0] != IMAGE_MAGIC) {
        return BP_IMAGE_NOT_FIRMWARE;
    }
    const uint32_t magic = (uint32_t)head[APP_DESC_OFFSET] |
                           (uint32_t)head[APP_DESC_OFFSET + 1] << 8 |
                           (uint32_t)head[APP_DESC_OFFSET + 2] << 16 |
                           (uint32_t)head[APP_DESC_OFFSET + 3] << 24;
    if (magic != APP_DESC_MAGIC) {
        return BP_IMAGE_NOT_FIRMWARE;
    }
    char image_version[APP_DESC_FIELD + 1];
    char project[APP_DESC_FIELD + 1];
    field(head + APP_DESC_VERSION, image_version, sizeof image_version);
    field(head + APP_DESC_PROJECT, project, sizeof project);
    if (version != NULL) {
        field(head + APP_DESC_VERSION, version, version_size);
    }
    if (strcmp(project, BP_PROJECT_NAME) != 0) {
        return BP_IMAGE_OTHER_PROJECT;
    }
    if (ends_with(image_version, BP_EMULATOR_VERSION_SUFFIX) != running_is_emulator) {
        return BP_IMAGE_WRONG_KIND;
    }
    return BP_IMAGE_OK;
}

const char *bp_image_check_reason(bp_image_check_t check, bool running_is_emulator)
{
    switch (check) {
    case BP_IMAGE_OK:
        return "A Boresight camera firmware.";
    case BP_IMAGE_NOT_FIRMWARE:
        return "Not a firmware image. Upload the app image (boresight-cam.bin), "
               "not the bootloader, the partition table or a merged image.";
    case BP_IMAGE_OTHER_PROJECT:
        return "A firmware, but not the Boresight camera's.";
    case BP_IMAGE_WRONG_KIND:
    default:
        return running_is_emulator ? "A board's firmware: this is the emulator, "
                                     "which takes only an emulator build."
                                   : "An emulator build: a board takes only a "
                                     "board's firmware (tools/idf.sh device build).";
    }
}
