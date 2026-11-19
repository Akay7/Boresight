#include "boresight_cam.h"
#include "driver/gpio.h"
#include "esp_camera.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/semphr.h"
#include "sdkconfig.h"

static const char *TAG = "camera";

/* AI-Thinker ESP32-CAM. A different board is a different table here. */
#define CAM_PIN_PWDN 32
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK 0
#define CAM_PIN_SIOD 26
#define CAM_PIN_SIOC 27
#define CAM_PIN_D7 35
#define CAM_PIN_D6 34
#define CAM_PIN_D5 39
#define CAM_PIN_D4 36
#define CAM_PIN_D3 21
#define CAM_PIN_D2 19
#define CAM_PIN_D1 18
#define CAM_PIN_D0 5
#define CAM_PIN_VSYNC 25
#define CAM_PIN_HREF 23
#define CAM_PIN_PCLK 22
#define FLASH_LED_GPIO 4

static framesize_t configured_frame_size(void)
{
    switch (settings()->resolution) {
    case BP_RES_VGA:
        return FRAMESIZE_VGA;
    case BP_RES_SVGA:
        return FRAMESIZE_SVGA;
    case BP_RES_HD:
        return FRAMESIZE_HD;
    case BP_RES_XGA:
    default:
        return FRAMESIZE_XGA;
    }
}

/* Held from a grab to its release, and by a pause or resume: the driver
 * must not be stopped under a frame being sent. */
static SemaphoreHandle_t s_lock;
static bool s_paused;

static esp_err_t start_driver(int *width, int *height)
{
    const camera_config_t config = {
        .pin_pwdn = CAM_PIN_PWDN,
        .pin_reset = CAM_PIN_RESET,
        .pin_xclk = CAM_PIN_XCLK,
        .pin_sccb_sda = CAM_PIN_SIOD,
        .pin_sccb_scl = CAM_PIN_SIOC,
        .pin_d7 = CAM_PIN_D7,
        .pin_d6 = CAM_PIN_D6,
        .pin_d5 = CAM_PIN_D5,
        .pin_d4 = CAM_PIN_D4,
        .pin_d3 = CAM_PIN_D3,
        .pin_d2 = CAM_PIN_D2,
        .pin_d1 = CAM_PIN_D1,
        .pin_d0 = CAM_PIN_D0,
        .pin_vsync = CAM_PIN_VSYNC,
        .pin_href = CAM_PIN_HREF,
        .pin_pclk = CAM_PIN_PCLK,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        /* Encoded by the sensor itself: no CPU spent on JPEG. */
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = configured_frame_size(),
        .jpeg_quality = settings()->jpeg_quality,
        .fb_count = 2,
        .fb_location = CAMERA_FB_IN_PSRAM,
        /* Overwrite unread frames rather than queue them. */
        .grab_mode = CAMERA_GRAB_LATEST,
    };

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "init failed: %s", esp_err_to_name(err));
        return err;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor == NULL) {
        ESP_LOGE(TAG, "no sensor after init");
        return ESP_FAIL;
    }

    /* Paper markers beside a bright panel: automatic exposure chases the
     * panel and the markers underexpose to mud. */
    sensor->set_exposure_ctrl(sensor, 0);
    sensor->set_aec2(sensor, 0);
    sensor->set_aec_value(sensor, settings()->exposure);
    sensor->set_gain_ctrl(sensor, 0);
    sensor->set_agc_gain(sensor, settings()->gain);

    /* Reported from what the sensor holds, not from what was asked for. */
    const camera_status_t *status = &sensor->status;
    *width = resolution[status->framesize].width;
    *height = resolution[status->framesize].height;
    ESP_LOGI(TAG,
             "applied: %dx%d, JPEG quality %d, auto exposure %s, exposure %d, "
             "auto gain %s, gain %d",
             *width, *height, status->quality, status->aec ? "ON" : "off",
             status->aec_value, status->agc ? "ON" : "off", status->agc_gain);
    if (status->aec || status->agc) {
        ESP_LOGW(TAG, "the sensor did not accept manual exposure or gain; "
                      "detection in a dim room will suffer");
    }
    return ESP_OK;
}

esp_err_t camera_start(int *width, int *height)
{
    /* The white flash LED. Left floating it can glow faintly, lighting the
     * markers differently from frame to frame; it is never used. */
    gpio_reset_pin(FLASH_LED_GPIO);
    gpio_set_direction(FLASH_LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(FLASH_LED_GPIO, 0);

    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    return start_driver(width, height);
}

void camera_pause(void)
{
    if (s_lock == NULL) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (!s_paused) {
        esp_camera_deinit();
        s_paused = true;
        ESP_LOGI(TAG, "paused");
    }
    xSemaphoreGive(s_lock);
}

void camera_resume(void)
{
    if (s_lock == NULL) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_paused) {
        int width;
        int height;
        if (start_driver(&width, &height) == ESP_OK) {
            s_paused = false;
        } else {
            /* Grabs keep failing, which the stream reports as skipped
             * frames; a restart starts the camera afresh. */
            ESP_LOGE(TAG, "did not start again after a pause");
        }
    }
    xSemaphoreGive(s_lock);
}

bool camera_grab(camera_frame_t *frame)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_paused) {
        xSemaphoreGive(s_lock);
        return false;
    }
    camera_fb_t *buffer = esp_camera_fb_get();
    if (buffer == NULL) {
        xSemaphoreGive(s_lock);
        return false;
    }
    frame->data = buffer->buf;
    frame->length = buffer->len;
    /* The driver stamps each frame from esp_timer as it is captured. With
     * CAMERA_GRAB_LATEST that can be most of a frame period before this
     * grab, and the server smooths aim by capture intervals. */
    double driver_ms = (double)buffer->timestamp.tv_sec * 1000.0 +
                       (double)buffer->timestamp.tv_usec / 1000.0;
    frame->captured_ms =
        bp_capture_ms(driver_ms, (double)esp_timer_get_time() / 1000.0);
    frame->handle = buffer;
    return true;
}

void camera_release(camera_frame_t *frame)
{
    esp_camera_fb_return((camera_fb_t *)frame->handle);
    frame->handle = NULL;
    xSemaphoreGive(s_lock);
}
