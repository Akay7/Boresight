/*
 * Push buttons, wired between a GPIO and GND with the internal pull-up.
 *
 * An edge interrupt wakes a high-priority task, which samples the pin
 * every millisecond until the debouncer settles, then sleeps until the
 * next edge. The trigger's latency is therefore the debounce time plus at
 * most one frame send, never a frame period. The trigger sends `down` on
 * press and `up` on release, so holding it holds the button.
 */
#include <stddef.h>

#include "boresight_cam.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "buttons";

typedef enum {
    BUTTON_ACTION_TRIGGER = 0,
} button_action_t;

typedef struct {
    const char *name;
    int gpio;
    button_action_t action;
    bp_debouncer_t debouncer;
    /* The link session a `down` went out on, 0 if none is outstanding.
     * An `up` is sent only on that same session: after a reconnect the
     * server has already let go, and the new session never held. */
    uint32_t down_session;
} button_t;

/* One entry per wired button. Only the trigger has an action: any other
 * needs a control message the server understands first. */
static button_t s_buttons[] = {
    {.name = "trigger",
     .gpio = CONFIG_BORESIGHT_TRIGGER_GPIO,
     .action = BUTTON_ACTION_TRIGGER},
};
#define BUTTON_COUNT (sizeof s_buttons / sizeof s_buttons[0])

static TaskHandle_t s_task;

#if CONFIG_BORESIGHT_EMULATOR
/* The level each button would read, set from the console. Only the pin
 * read is replaced; everything the level feeds is the real code. */
static volatile bool s_injected[BUTTON_COUNT];

void buttons_inject(size_t index, bool pressed)
{
    if (index >= BUTTON_COUNT || s_task == NULL) {
        return;
    }
    s_injected[index] = pressed;
    /* What the edge interrupt does on a board. */
    xTaskNotifyGive(s_task);
}
#endif

static void IRAM_ATTR on_edge(void *arg)
{
    (void)arg;
    BaseType_t woken = pdFALSE;
    vTaskNotifyGiveFromISR(s_task, &woken);
    portYIELD_FROM_ISR(woken);
}

static bool is_pressed(const button_t *button)
{
#if CONFIG_BORESIGHT_EMULATOR
    return s_injected[button - s_buttons];
#else
    return gpio_get_level(button->gpio) == 0; /* active-low */
#endif
}

static void press(button_t *button)
{
    switch (button->action) {
    case BUTTON_ACTION_TRIGGER:
        /* Not queued for later: a press delivered after a reconnect lands
         * wherever the cursor happens to be by then. */
        if (!link_is_streaming()) {
            ESP_LOGW(TAG, "%s pressed while disconnected: discarded", button->name);
            return;
        }
        /* Recorded even if the send fails: a failed send may still have
         * reached the server, and an `up` it did not need is ignored,
         * while a missing one would leave the button down. */
        button->down_session = link_session_id();
        if (link_send_trigger_down(CONFIG_BORESIGHT_SEND_TIMEOUT_MS + 50) != ESP_OK) {
            ESP_LOGW(TAG, "%s press was not delivered", button->name);
        }
        break;
    }
}

static void release(button_t *button)
{
    switch (button->action) {
    case BUTTON_ACTION_TRIGGER: {
        uint32_t session = button->down_session;
        button->down_session = 0;
        if (session == 0 || session != link_session_id() || !link_is_streaming()) {
            /* Never pressed on this connection, or the connection it was
             * pressed on is gone and took the hold with it. */
            return;
        }
        if (link_send_text(BP_TRIGGER_UP_MESSAGE,
                           CONFIG_BORESIGHT_SEND_TIMEOUT_MS + 50) != ESP_OK) {
            /* The server lets go on its own once this session ends or
             * goes quiet; nothing better to do from here. */
            ESP_LOGW(TAG, "%s release was not delivered", button->name);
        }
        break;
    }
    }
}

static void button_task(void *arg)
{
    (void)arg;
    uint32_t now = boresight_now_ms();
    for (size_t i = 0; i < BUTTON_COUNT; i++) {
        bp_debounce_init(&s_buttons[i].debouncer, CONFIG_BORESIGHT_DEBOUNCE_MS,
                         is_pressed(&s_buttons[i]), now);
    }

    for (;;) {
        bool settling = false;
        for (size_t i = 0; i < BUTTON_COUNT; i++) {
            settling = settling || bp_debounce_settling(&s_buttons[i].debouncer);
        }
        ulTaskNotifyTake(pdTRUE, settling ? pdMS_TO_TICKS(1) : portMAX_DELAY);

        now = boresight_now_ms();
        for (size_t i = 0; i < BUTTON_COUNT; i++) {
            button_t *button = &s_buttons[i];
            switch (bp_debounce_update(&button->debouncer, is_pressed(button), now)) {
            case BP_BUTTON_PRESSED:
                press(button);
                break;
            case BP_BUTTON_RELEASED:
                release(button);
                break;
            case BP_BUTTON_NONE:
                break;
            }
        }
    }
}

bool buttons_valid(void)
{
    bool valid = true;
    for (size_t i = 0; i < BUTTON_COUNT; i++) {
        if (!bp_button_gpio_allowed(s_buttons[i].gpio)) {
            ESP_LOGE(TAG,
                     "%s button on GPIO%d: on the AI-Thinker ESP32-CAM that pin "
                     "belongs to the camera, PSRAM, serial console, flash LED or "
                     "a boot strap. Use GPIO13 or GPIO14.",
                     s_buttons[i].name, s_buttons[i].gpio);
            valid = false;
        }
        for (size_t j = 0; j < i; j++) {
            if (s_buttons[j].gpio == s_buttons[i].gpio) {
                ESP_LOGE(TAG, "%s and %s buttons share GPIO%d", s_buttons[j].name,
                         s_buttons[i].name, s_buttons[i].gpio);
                valid = false;
            }
        }
    }
    return valid;
}

esp_err_t buttons_start(void)
{
    /* Pins first, with interrupts off, so the task reads settled levels;
     * the task before the interrupts, so an early edge has a task to wake. */
    for (size_t i = 0; i < BUTTON_COUNT; i++) {
        const gpio_config_t io = {
            .pin_bit_mask = 1ULL << s_buttons[i].gpio,
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_RETURN_ON_ERROR(gpio_config(&io), TAG, "configure GPIO%d",
                            s_buttons[i].gpio);
    }

    if (xTaskCreate(button_task, "buttons", 3072, NULL, 10, &s_task) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    /* Already installed by the camera driver is fine. */
    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }
    for (size_t i = 0; i < BUTTON_COUNT; i++) {
        int gpio = s_buttons[i].gpio;
        ESP_RETURN_ON_ERROR(gpio_isr_handler_add(gpio, on_edge, NULL), TAG,
                            "interrupt on GPIO%d", gpio);
        ESP_RETURN_ON_ERROR(gpio_set_intr_type(gpio, GPIO_INTR_ANYEDGE), TAG,
                            "edge on GPIO%d", gpio);
        ESP_LOGI(TAG, "%s button on GPIO%d", s_buttons[i].name, gpio);
    }
    return ESP_OK;
}
