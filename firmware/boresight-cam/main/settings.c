/*
 * The device's effective settings: the defaults, with whatever setup mode
 * stored on the device laid over them. On a board the defaults have no
 * network at all -- Wi-Fi, server and token come only from setup mode --
 * and the camera's come from the build configuration. The emulator also
 * builds in the server it reaches.
 *
 * Each setting is its own NVS key in the "boresight" namespace, present
 * only when it differs from the build's value, so a setting nobody changed
 * on the device keeps following the build. Erasing that namespace (and
 * only that one: Wi-Fi and the PHY keep their own data in the same
 * partition) is "reset to build defaults".
 */
#include <inttypes.h>
#include <string.h>

#include "boresight_cam.h"
#include "esp_log.h"
#include "nvs.h"
#include "sdkconfig.h"

static const char *TAG = "settings";

#define NAMESPACE "boresight"
#define KEY_SSID "ssid"
#define KEY_PASSWORD "pass"
#define KEY_HOST "host"
#define KEY_PORT "port"
#define KEY_TOKEN "token"
#define KEY_RESOLUTION "res"
#define KEY_JPEG_QUALITY "jpegq"
#define KEY_MAX_FPS "fps"
#define KEY_EXPOSURE "aec"
#define KEY_GAIN "agc"
/* Emulator only: the `setup` console command's request, read once. */
#define KEY_SETUP_NEXT "setup_next"

#if !CONFIG_BORESIGHT_EMULATOR
/* The server's own default port (DEFAULT_PORT, src/boresight/netaccess.py):
 * a board connects there until another port is stored. */
#define DEFAULT_SERVER_PORT 7331
#endif

/* The ranges main/Kconfig.projbuild gives these options; kept in step by
 * hand, since Kconfig ranges do not reach C. */
static const bp_camera_limits_t LIMITS = {
    .jpeg_quality = {4, 63},
    .max_fps = {1, 30},
    .exposure = {0, 1200},
    .gain = {0, 30},
};

static bp_settings_t s_build;
static bp_settings_t s_effective;

static bp_resolution_t build_resolution(void)
{
#if CONFIG_BORESIGHT_FRAME_SIZE_VGA
    return BP_RES_VGA;
#elif CONFIG_BORESIGHT_FRAME_SIZE_SVGA
    return BP_RES_SVGA;
#elif CONFIG_BORESIGHT_FRAME_SIZE_HD
    return BP_RES_HD;
#else
    return BP_RES_XGA;
#endif
}

void settings_build_defaults(bp_settings_t *out)
{
    memset(out, 0, sizeof *out);
#if CONFIG_BORESIGHT_EMULATOR
    /* The server QEMU's user networking reaches (sdkconfig.emulator), so
     * the end-to-end suite starts connected. */
    strlcpy(out->host, CONFIG_BORESIGHT_SERVER_HOST, sizeof out->host);
    out->port = CONFIG_BORESIGHT_SERVER_PORT;
    strlcpy(out->token, CONFIG_BORESIGHT_TOKEN, sizeof out->token);
#else
    /* A board's network comes only from setup mode: no Wi-Fi, address or
     * token here, so no image carries them, and the port is the server's
     * own default until one is stored. */
    out->port = DEFAULT_SERVER_PORT;
#endif
    out->resolution = build_resolution();
    out->jpeg_quality = CONFIG_BORESIGHT_JPEG_QUALITY;
    out->max_fps = CONFIG_BORESIGHT_MAX_FPS;
    out->exposure = CONFIG_BORESIGHT_AEC_VALUE;
    out->gain = CONFIG_BORESIGHT_AGC_GAIN;
}

const bp_settings_t *settings(void)
{
    return &s_effective;
}

const bp_camera_limits_t *settings_camera_limits(void)
{
    return &LIMITS;
}

/* A stored string, if present and acceptable to `valid`; anything else
 * leaves `out` as it was. True when the device's value is in effect. */
static bool load_string(nvs_handle_t handle, const char *key, char *out, size_t size,
                        bool (*valid)(const char *))
{
    char value[BP_TOKEN_MAX + 1];
    size_t length = sizeof value;
    if (nvs_get_str(handle, key, value, &length) != ESP_OK) {
        return false;
    }
    if (length > size || (valid != NULL && !valid(value))) {
        ESP_LOGW(TAG, "ignoring the stored %s: not a valid value", key);
        return false;
    }
    strlcpy(out, value, size);
    return true;
}

static bool load_int(nvs_handle_t handle, const char *key, bp_range_t range, int *out)
{
    int32_t value = 0;
    if (nvs_get_i32(handle, key, &value) != ESP_OK) {
        return false;
    }
    if (value < range.min || value > range.max) {
        ESP_LOGW(TAG, "ignoring the stored %s: %" PRIi32 " is out of range", key,
                 value);
        return false;
    }
    *out = (int)value;
    return true;
}

static const char *source(bool stored)
{
    return stored ? "device" : "build";
}

void settings_load(void)
{
    settings_build_defaults(&s_build);
    s_effective = s_build;

    nvs_handle_t handle;
    bool ssid = false, password = false, host = false, port = false, token = false;
    bool resolution = false, quality = false, fps = false, exposure = false,
         gain = false;
    if (nvs_open(NAMESPACE, NVS_READONLY, &handle) == ESP_OK) {
        bp_settings_t *s = &s_effective;
        ssid = load_string(handle, KEY_SSID, s->ssid, sizeof s->ssid, bp_ssid_valid);
        password = load_string(handle, KEY_PASSWORD, s->password, sizeof s->password,
                               bp_password_valid);
        host = load_string(handle, KEY_HOST, s->host, sizeof s->host, bp_host_valid);
        token = load_string(handle, KEY_TOKEN, s->token, sizeof s->token,
                            bp_token_valid);
        int value = s->port;
        port = load_int(handle, KEY_PORT, (bp_range_t){1, 65535}, &value);
        s->port = (uint16_t)value;
        value = (int)s->resolution;
        resolution =
            load_int(handle, KEY_RESOLUTION, (bp_range_t){0, BP_RES_COUNT - 1}, &value);
        s->resolution = (bp_resolution_t)value;
        quality = load_int(handle, KEY_JPEG_QUALITY, LIMITS.jpeg_quality,
                           &s->jpeg_quality);
        fps = load_int(handle, KEY_MAX_FPS, LIMITS.max_fps, &s->max_fps);
        exposure = load_int(handle, KEY_EXPOSURE, LIMITS.exposure, &s->exposure);
        gain = load_int(handle, KEY_GAIN, LIMITS.gain, &s->gain);
        nvs_close(handle);
    }

    /* Where each value came from, so a menuconfig change that does not
     * seem to take is explained by a value stored on the device. Secrets
     * are only said to be set or not. */
    const bp_settings_t *s = &s_effective;
#if CONFIG_BORESIGHT_EMULATOR
    (void)ssid; /* no Wi-Fi in the emulator */
    (void)password;
    ESP_LOGI(TAG, "server \"%s\" (%s), port %u (%s), token %s (%s)",
             s->host[0] ? s->host : "(discover)", source(host), (unsigned)s->port,
             source(port), s->token[0] ? "set" : "not set", source(token));
#else
    /* A board's network has one source, the device: a value is stored
     * there or not set at all, and the port is the default until stored. */
    if (ssid) {
        ESP_LOGI(TAG, "wifi \"%s\" (device), password %s", s->ssid,
                 password ? "set (device)" : "not set");
    } else {
        ESP_LOGI(TAG, "wifi not set");
    }
    const char *port_source = port ? "device" : "default";
    const char *token_state = token ? "set (device)" : "not set";
    if (host) {
        ESP_LOGI(TAG, "server \"%s\" (device), port %u (%s), token %s", s->host,
                 (unsigned)s->port, port_source, token_state);
    } else {
        ESP_LOGI(TAG, "server not set: discover, port %u (%s), token %s",
                 (unsigned)s->port, port_source, token_state);
    }
#endif
    ESP_LOGI(TAG,
             "camera %s (%s), quality %d (%s), max %d fps (%s), exposure %d (%s), "
             "gain %d (%s)",
             bp_resolution_name(s->resolution), source(resolution), s->jpeg_quality,
             source(quality), s->max_fps, source(fps), s->exposure, source(exposure),
             s->gain, source(gain));
}

/* Stores `value` under `key` when it differs from the build's, and removes
 * the key when it is the build's again. */
static esp_err_t store_string(nvs_handle_t handle, const char *key, const char *value,
                              const char *build)
{
    if (strcmp(value, build) == 0) {
        esp_err_t err = nvs_erase_key(handle, key);
        return err == ESP_ERR_NVS_NOT_FOUND ? ESP_OK : err;
    }
    return nvs_set_str(handle, key, value);
}

static esp_err_t store_int(nvs_handle_t handle, const char *key, int value, int build)
{
    if (value == build) {
        esp_err_t err = nvs_erase_key(handle, key);
        return err == ESP_ERR_NVS_NOT_FOUND ? ESP_OK : err;
    }
    return nvs_set_i32(handle, key, value);
}

esp_err_t settings_save(const bp_settings_t *s)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }
    const bp_settings_t *b = &s_build;
    const esp_err_t results[] = {
        store_string(handle, KEY_SSID, s->ssid, b->ssid),
        store_string(handle, KEY_PASSWORD, s->password, b->password),
        store_string(handle, KEY_HOST, s->host, b->host),
        store_int(handle, KEY_PORT, s->port, b->port),
        store_string(handle, KEY_TOKEN, s->token, b->token),
        store_int(handle, KEY_RESOLUTION, (int)s->resolution, (int)b->resolution),
        store_int(handle, KEY_JPEG_QUALITY, s->jpeg_quality, b->jpeg_quality),
        store_int(handle, KEY_MAX_FPS, s->max_fps, b->max_fps),
        store_int(handle, KEY_EXPOSURE, s->exposure, b->exposure),
        store_int(handle, KEY_GAIN, s->gain, b->gain),
    };
    for (size_t i = 0; i < sizeof results / sizeof results[0]; i++) {
        if (results[i] != ESP_OK) {
            err = results[i];
        }
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    if (err == ESP_OK) {
        s_effective = *s;
        ESP_LOGI(TAG, "settings stored on the device");
    } else {
        ESP_LOGE(TAG, "storing the settings failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t settings_erase(void)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_erase_all(handle);
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    if (err == ESP_OK) {
        s_effective = s_build;
        ESP_LOGI(TAG, "settings stored on the device erased: build defaults apply");
    }
    return err;
}

esp_err_t settings_request_setup(void)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_set_u8(handle, KEY_SETUP_NEXT, 1);
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    return err;
}

bool settings_take_setup_request(void)
{
    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        return false;
    }
    uint8_t value = 0;
    const bool requested = nvs_get_u8(handle, KEY_SETUP_NEXT, &value) == ESP_OK;
    if (requested) {
        nvs_erase_key(handle, KEY_SETUP_NEXT);
        nvs_commit(handle);
    }
    nvs_close(handle);
    return requested && value == 1;
}
