/*
 * Firmware updates over Wi-Fi: writing an uploaded image to the slot not
 * running, switching to it, and keeping it only once it has proved it
 * starts.
 *
 * Two application slots (partitions.csv) and the bootloader's rollback
 * do the heavy lifting. A newly installed image boots "pending": if it
 * resets before ota_mark_good() -- called on first reaching the server or
 * once setup mode's page is up -- the bootloader returns to the previous
 * slot by itself. The version being installed is kept in NVS until then,
 * which is how the next boot can tell, and say, that an update was rolled
 * back.
 */
#include <string.h>

#include "boresight_cam.h"
#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "nvs.h"
#include "sdkconfig.h"

static const char *TAG = "ota";

/* Apart from the settings: "reset to build defaults" must not forget an
 * update in progress. */
#define NAMESPACE "boresight_ota"
#define KEY_PENDING_SLOT "slot"
#define KEY_PENDING_VERSION "version"

static esp_ota_handle_t s_handle;
static const esp_partition_t *s_target;
static bool s_marked_good;
static char s_version[33];

static void forget_pending(void)
{
    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) == ESP_OK) {
        nvs_erase_key(handle, KEY_PENDING_SLOT);
        nvs_erase_key(handle, KEY_PENDING_VERSION);
        nvs_commit(handle);
        nvs_close(handle);
    }
}

void ota_boot_report(void)
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    const char *version = esp_app_get_description()->version;
    ESP_LOGI(TAG, "running %s from %s", version, running ? running->label : "?");

    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READONLY, &handle) != ESP_OK) {
        return;
    }
    char slot[17];
    char pending[33];
    size_t slot_length = sizeof slot;
    size_t version_length = sizeof pending;
    const bool have =
        nvs_get_str(handle, KEY_PENDING_SLOT, slot, &slot_length) == ESP_OK &&
        nvs_get_str(handle, KEY_PENDING_VERSION, pending, &version_length) == ESP_OK;
    nvs_close(handle);
    if (have && running != NULL && strcmp(slot, running->label) != 0) {
        /* The bootloader went back: the new image reset before it was
         * marked good. */
        ESP_LOGE(TAG, "update to %s in %s did not start: rolled back to %s in %s",
                 pending, slot, version, running->label);
        forget_pending();
    }
}

void ota_mark_good(void)
{
    if (s_marked_good) {
        return;
    }
    s_marked_good = true;
    esp_ota_img_states_t state;
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (running != NULL && esp_ota_get_state_partition(running, &state) == ESP_OK &&
        state == ESP_OTA_IMG_PENDING_VERIFY) {
        /* Marking it erases a flash sector: with the camera running, its
         * interrupt crashed the board mid-erase (see camera_pause), and
         * the bootloader then rolled back an update that had worked. */
        camera_pause();
        const esp_err_t err = esp_ota_mark_app_valid_cancel_rollback();
        forget_pending();
        camera_resume();
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "firmware %s started: kept",
                     esp_app_get_description()->version);
        }
        return;
    }
    forget_pending();
}

esp_err_t ota_upload_begin(const uint8_t *head, size_t length, size_t total,
                           const char **reason)
{
    const bp_image_check_t check = bp_app_image_check(
        head, length, BORESIGHT_IS_EMULATOR, s_version, sizeof s_version);
    if (check != BP_IMAGE_OK) {
        *reason = bp_image_check_reason(check, BORESIGHT_IS_EMULATOR);
        ESP_LOGW(TAG, "upload refused: %s", *reason);
        return ESP_ERR_INVALID_ARG;
    }
    s_target = esp_ota_get_next_update_partition(NULL);
    if (s_target == NULL) {
        *reason = "This device has no second firmware slot: it needs one flash over "
                  "the adapter to the new layout before it can update over Wi-Fi.";
        return ESP_ERR_NOT_FOUND;
    }
    if (total > s_target->size) {
        *reason = "The image is larger than a firmware slot.";
        return ESP_ERR_INVALID_SIZE;
    }
    /* Erased as it is written, so a slow phone does not wait for the
     * whole slot to be cleared first. */
    esp_err_t err = esp_ota_begin(s_target, OTA_WITH_SEQUENTIAL_WRITES, &s_handle);
    if (err != ESP_OK) {
        *reason = "The firmware slot could not be prepared.";
        return err;
    }
    ESP_LOGI(TAG, "receiving %s (%u bytes) into %s", s_version, (unsigned)total,
             s_target->label);
    return ESP_OK;
}

esp_err_t ota_upload_write(const void *data, size_t length)
{
    return esp_ota_write(s_handle, data, length);
}

void ota_upload_abort(void)
{
    if (s_handle != 0) {
        esp_ota_abort(s_handle);
        s_handle = 0;
    }
}

esp_err_t ota_upload_finish(const char **reason)
{
    /* Checks the length, the checksum and the image's SHA-256: a cut-off
     * or damaged upload fails here, with the boot slot untouched. */
    esp_err_t err = esp_ota_end(s_handle);
    s_handle = 0;
    if (err != ESP_OK) {
        *reason = err == ESP_ERR_OTA_VALIDATE_FAILED
                      ? "The image is incomplete or damaged: nothing was changed."
                      : "The image could not be written: nothing was changed.";
        ESP_LOGW(TAG, "upload not installed: %s", esp_err_to_name(err));
        return err;
    }
    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) == ESP_OK) {
        nvs_set_str(handle, KEY_PENDING_SLOT, s_target->label);
        nvs_set_str(handle, KEY_PENDING_VERSION, s_version);
        nvs_commit(handle);
        nvs_close(handle);
    }
    err = esp_ota_set_boot_partition(s_target);
    if (err != ESP_OK) {
        forget_pending();
        *reason = "The new firmware could not be selected: nothing was changed.";
        return err;
    }
    ESP_LOGI(TAG, "%s installed in %s: restarting into it", s_version,
             s_target->label);
    return ESP_OK;
}

const char *ota_upload_version(void)
{
    return s_version;
}
