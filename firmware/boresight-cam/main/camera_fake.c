/*
 * Emulator build only: the camera sensor, replaced by rendered frames.
 *
 * Serves frames of tests/fixtures/esp32cam_video -- the project's Blender
 * scene rendered as the ESP32-CAM sees it -- in order, repeating.
 * Everything after the sensor is the real firmware: pacing, the frame
 * header, the fragmented send. Never blocks: the capture loop already
 * paces to the frame-rate cap.
 */
#include "boresight_cam.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "camera";

/* Embedded by main/CMakeLists.txt, which must list the same frames. */
#define FRAME(n)                                                                 \
    extern const uint8_t frame_##n##_start[] asm("_binary_frame_000" #n "_jpg_start"); \
    extern const uint8_t frame_##n##_end[] asm("_binary_frame_000" #n "_jpg_end");
FRAME(1)
FRAME(2)
FRAME(3)
FRAME(4)
FRAME(5)
FRAME(6)
FRAME(7)
FRAME(8)

static const struct {
    const uint8_t *start;
    const uint8_t *end;
} s_frames[] = {
    {frame_1_start, frame_1_end}, {frame_2_start, frame_2_end},
    {frame_3_start, frame_3_end}, {frame_4_start, frame_4_end},
    {frame_5_start, frame_5_end}, {frame_6_start, frame_6_end},
    {frame_7_start, frame_7_end}, {frame_8_start, frame_8_end},
};
#define FRAME_COUNT (sizeof s_frames / sizeof s_frames[0])

static size_t s_next;

esp_err_t camera_start(int *width, int *height)
{
    /* Read from the frames, not configured: what `hello` reports has to be
     * what the server will decode. */
    for (size_t i = 0; i < FRAME_COUNT; i++) {
        int frame_width = 0;
        int frame_height = 0;
        if (!bp_jpeg_dimensions(s_frames[i].start,
                                (size_t)(s_frames[i].end - s_frames[i].start),
                                &frame_width, &frame_height)) {
            ESP_LOGE(TAG, "embedded frame %u is not a readable JPEG", (unsigned)i + 1);
            return ESP_FAIL;
        }
        if (i == 0) {
            *width = frame_width;
            *height = frame_height;
        } else if (frame_width != *width || frame_height != *height) {
            ESP_LOGE(TAG, "embedded frames differ in size (%dx%d vs %dx%d)",
                     frame_width, frame_height, *width, *height);
            return ESP_FAIL;
        }
    }
    ESP_LOGW(TAG, "fake camera: %u recorded %dx%d frames in place of the sensor",
             (unsigned)FRAME_COUNT, *width, *height);
    return ESP_OK;
}

bool camera_grab(camera_frame_t *frame)
{
    frame->data = s_frames[s_next].start;
    frame->length = (size_t)(s_frames[s_next].end - s_frames[s_next].start);
    /* No sensor, so no capture time: the grab is the capture. */
    frame->captured_ms = (double)esp_timer_get_time() / 1000.0;
    frame->handle = NULL;
    s_next = (s_next + 1) % FRAME_COUNT;
    return true;
}

void camera_release(camera_frame_t *frame)
{
    (void)frame;
}
