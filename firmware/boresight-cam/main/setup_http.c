/*
 * The setup page: what setup mode serves on its network.
 *
 *   GET  /       the form, with the settings in effect
 *   GET  /scan   look for networks again (boards), then back to /
 *   POST /save   check everything, store, confirm, restart
 *   POST /reset  forget everything stored, confirm, restart
 *   POST /update a firmware image as the raw body: check, install in the
 *                slot not running, confirm, restart into it
 *   anything else: a redirect to the page, which is what turns a phone's
 *   sign-in check into the setup page
 *
 * One plain HTML page with its own styles: the phone has no internet on
 * this network, so nothing can come from anywhere else. Only the firmware
 * upload uses a few lines of inline script, to send the file as it is and
 * show progress; every other form works without it.
 * Every value echoed into it is escaped (scanned network names come from
 * strangers' access points), and the stored password and token are never
 * in it -- only whether each is set.
 */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "boresight_cam.h"
#include "esp_app_desc.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "sdkconfig.h"

/* A phone browser's request headers do not fit in 512 bytes, and an
 * oversized request is refused before any handler runs: the page would
 * simply not open. sdkconfig.defaults sets 1024; a configuration made
 * before that keeps its old value until it is changed. */
#if CONFIG_HTTPD_MAX_REQ_HDR_LEN < 1024
#error "Setup mode needs CONFIG_HTTPD_MAX_REQ_HDR_LEN >= 1024: set it in menuconfig \
(Component config -> HTTP Server -> Max HTTP Request Header Length) or in sdkconfig."
#endif

static const char *TAG = "setup_http";

/* The longest form the page can post, every field at its limit and fully
 * percent-encoded, with room to spare. */
#define BODY_MAX 1536

static httpd_handle_t s_server;
static const char *s_home;
static char s_body[BODY_MAX + 1]; /* the server handles one request at a time */
static uint8_t s_chunk[4096];      /* likewise: a firmware upload in pieces */

static const char STYLE[] =
    "<style>"
    "body{font:16px/1.4 system-ui,sans-serif;margin:0 auto;max-width:34em;"
    "padding:1em;color:#111;background:#fff}"
    "h1{font-size:1.4em}fieldset{border:1px solid #ccc;border-radius:6px;"
    "margin:0 0 1em}label{display:block;margin:.6em 0}"
    "input,select,button{font:inherit;width:100%;box-sizing:border-box;"
    "padding:.4em}input[type=checkbox]{width:auto}"
    "button{background:#1f77b4;color:#fff;border:0;border-radius:6px;"
    "padding:.7em;margin-top:.5em}.secondary{background:#666}"
    ".err{color:#b00;display:block}.banner{background:#fee;padding:.6em;"
    "border-radius:6px}.note{color:#555;font-size:.9em}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}"
    "fieldset{border-color:#444}.banner{background:#422}.note{color:#aaa}"
    ".err{color:#f77}}"
    "</style>";

static esp_err_t send(httpd_req_t *req, const char *text)
{
    /* An empty chunk is the end of a chunked response: an empty value
     * (no network name yet) would cut the page off right there. */
    if (text[0] == '\0') {
        return ESP_OK;
    }
    return httpd_resp_send_chunk(req, text, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t send_escaped(httpd_req_t *req, const char *text)
{
    char escaped[BP_TOKEN_MAX * 6 + 1];
    if (bp_html_escape(text, escaped, sizeof escaped) < 0) {
        return send(req, "");
    }
    return send(req, escaped);
}

static void page_start(httpd_req_t *req, const char *title)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    send(req, "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
              "<meta name=\"viewport\" content=\"width=device-width,"
              "initial-scale=1\"><title>");
    send_escaped(req, title);
    send(req, "</title>");
    send(req, STYLE);
    send(req, "</head><body>");
}

static esp_err_t page_end(httpd_req_t *req)
{
    send(req, "</body></html>");
    return httpd_resp_send_chunk(req, NULL, 0);
}

/* --- The form ---------------------------------------------------------- */

/* What a field shows: what was just posted, when the page comes back with
 * errors, so nothing typed is lost; otherwise the setting in effect. */
static const char *field_value(const char *body, bp_field_t field, const char *current,
                               char *buffer, size_t size)
{
    if (body != NULL && bp_form_get(body, bp_field_name(field), buffer, size) >= 0) {
        return buffer;
    }
    return current;
}

static void error_for(httpd_req_t *req, bp_field_set_t invalid, bp_field_t field,
                      const char *message)
{
    if (invalid & (1u << field)) {
        send(req, "<span class=\"err\">");
        send_escaped(req, message);
        send(req, "</span>");
    }
}

static void text_input(httpd_req_t *req, const char *label, bp_field_t field,
                       const char *value, const char *extra)
{
    send(req, "<label>");
    send(req, label);
    send(req, "<input name=\"");
    send(req, bp_field_name(field));
    send(req, "\" value=\"");
    send_escaped(req, value);
    send(req, "\" ");
    send(req, extra);
    send(req, "></label>");
}

static void number_input(httpd_req_t *req, const char *label, bp_field_t field,
                         const char *body, int current, bp_range_t range,
                         bp_field_set_t invalid)
{
    char now[16];
    char posted[16];
    char extra[64];
    snprintf(now, sizeof now, "%d", current);
    snprintf(extra, sizeof extra, "type=\"number\" min=\"%d\" max=\"%d\"", range.min,
             range.max);
    text_input(req, label, field, field_value(body, field, now, posted, sizeof posted),
               extra);
    char message[48];
    snprintf(message, sizeof message, "A whole number from %d to %d.", range.min,
             range.max);
    error_for(req, invalid, field, message);
}

static void secret_input(httpd_req_t *req, const char *label, bp_field_t field,
                         bool is_set, const char *clear_name, const char *clear_label,
                         const char *extra)
{
    send(req, "<label>");
    send(req, label);
    send(req, is_set ? " <span class=\"note\">(set: leave empty to keep it)</span>"
                     : " <span class=\"note\">(not set)</span>");
    send(req, "<input type=\"password\" autocomplete=\"off\" name=\"");
    send(req, bp_field_name(field));
    send(req, "\" ");
    send(req, extra);
    send(req, "></label><label><input type=\"checkbox\" value=\"1\" name=\"");
    send(req, clear_name);
    send(req, "\"> ");
    send(req, clear_label);
    send(req, "</label>");
}

static esp_err_t send_form(httpd_req_t *req, const char *body, bp_field_set_t invalid)
{
    const bp_settings_t *s = settings();
    const bp_camera_limits_t *limits = settings_camera_limits();
    char buffer[BP_HOST_MAX + 1];

    page_start(req, "Boresight camera setup");
    send(req, "<h1>Boresight camera</h1><p class=\"note\">This setup network closes "
              "when you save, or by itself 10 minutes after it opened.</p>");
    if (invalid != 0) {
        send(req, "<p class=\"banner\">Nothing was saved: fix the fields marked "
                  "below.</p>");
    }
    send(req, "<form method=\"post\" action=\"/save\"><fieldset><legend>Wi-Fi"
              "</legend>");

    text_input(req, "Network (2.4 GHz)", BP_FIELD_SSID,
               field_value(body, BP_FIELD_SSID, s->ssid, buffer, sizeof buffer),
               "list=\"networks\" maxlength=\"32\" required");
    error_for(req, invalid, BP_FIELD_SSID, "1 to 32 characters.");
    send(req, "<datalist id=\"networks\">");
    static char networks[SETUP_MAX_NETWORKS][BP_SSID_MAX + 1];
    size_t count = setup_networks(networks, SETUP_MAX_NETWORKS);
    for (size_t i = 0; i < count; i++) {
        send(req, "<option value=\"");
        send_escaped(req, networks[i]);
        send(req, "\">");
    }
    send(req, "</datalist>");
#if !CONFIG_BORESIGHT_EMULATOR
    send(req, "<p class=\"note\">Pick from the list or type a name. "
              "<a href=\"/scan\">Look for networks again</a></p>");
#endif
    secret_input(req, "Password", BP_FIELD_PASSWORD, s->password[0] != '\0',
                 "clear_password", "Open network: no password",
                 "maxlength=\"63\"");
    error_for(req, invalid, BP_FIELD_PASSWORD,
              "8 to 63 characters, or none for an open network.");

    send(req, "</fieldset><fieldset><legend>Server</legend>");
    text_input(req, "Address", BP_FIELD_HOST,
               field_value(body, BP_FIELD_HOST, s->host, buffer, sizeof buffer),
               "maxlength=\"63\" placeholder=\"empty: find it on the network\"");
    error_for(req, invalid, BP_FIELD_HOST,
              "An address like 192.168.1.20, a host name, or empty.");
    number_input(req, "Port", BP_FIELD_PORT, body, s->port, (bp_range_t){1, 65535},
                 invalid);
    secret_input(req, "Token", BP_FIELD_TOKEN, s->token[0] != '\0', "clear_token",
                 "No token", "maxlength=\"128\"");
    error_for(req, invalid, BP_FIELD_TOKEN,
              "Letters, digits and - . _ ~ only, at most 128.");

    send(req, "</fieldset><fieldset><legend>Camera</legend><label>Resolution"
              "<select name=\"resolution\">");
    char posted[16];
    const char *resolution =
        field_value(body, BP_FIELD_RESOLUTION, bp_resolution_name(s->resolution),
                    posted, sizeof posted);
    for (int r = 0; r < BP_RES_COUNT; r++) {
        const char *name = bp_resolution_name((bp_resolution_t)r);
        send(req, strcmp(name, resolution) == 0 ? "<option selected>" : "<option>");
        send(req, name);
        send(req, "</option>");
    }
    send(req, "</select></label>");
    error_for(req, invalid, BP_FIELD_RESOLUTION, "Pick one of the listed sizes.");
    number_input(req, "JPEG quality (lower is better and larger)",
                 BP_FIELD_JPEG_QUALITY, body, s->jpeg_quality, limits->jpeg_quality,
                 invalid);
    number_input(req, "Frame rate cap", BP_FIELD_MAX_FPS, body, s->max_fps,
                 limits->max_fps, invalid);
    number_input(req, "Exposure (sensor units)", BP_FIELD_EXPOSURE, body, s->exposure,
                 limits->exposure, invalid);
    number_input(req, "Gain", BP_FIELD_GAIN, body, s->gain, limits->gain, invalid);

    send(req, "</fieldset><button>Save and restart</button></form>"
              "<form method=\"post\" action=\"/reset\"><button class=\"secondary\">"
              "Reset to build defaults</button></form>"
#if CONFIG_BORESIGHT_EMULATOR
              "<p class=\"note\">Reset forgets everything saved here; the device "
              "then uses the values it was built with.</p>"
#else
              "<p class=\"note\">Reset forgets everything saved here, the Wi-Fi, "
              "server and token included: the device restarts into this setup "
              "page, with the camera back at the values it was built with.</p>"
#endif
    );

    /* The firmware upload. Sent as the raw file by the script below; the
     * setup network has nothing else to load a script from. */
    send(req, "<fieldset><legend>Firmware</legend><p class=\"note\">Running ");
    send_escaped(req, esp_app_get_description()->version);
    send(req, ". To replace it, choose the app image (<code>boresight-cam.bin</code>"
              "); settings are kept, and a firmware that does not start is "
              "replaced by this one again.</p><label>Firmware file<input type="
              "\"file\" id=\"firmware\" accept=\".bin\"></label><button type="
              "\"button\" id=\"upload\">Upload and restart</button><p id="
              "\"progress\" class=\"note\"></p></fieldset>"
              "<script>document.getElementById('upload').onclick=function(){"
              "var f=document.getElementById('firmware').files[0],"
              "p=document.getElementById('progress');"
              "if(!f){p.textContent='Choose the firmware file first.';return;}"
              "var x=new XMLHttpRequest();x.open('POST','/update');"
              "x.setRequestHeader('Content-Type','application/octet-stream');"
              "x.upload.onprogress=function(e){if(e.lengthComputable)"
              "p.textContent='Uploading: '+Math.round(e.loaded*100/e.total)+'%';};"
              "x.onload=function(){document.open();document.write(x.responseText);"
              "document.close();};"
              "x.onerror=function(){p.textContent='The upload did not complete: "
              "the device kept its firmware.';};x.send(f);};</script>");
    return page_end(req);
}

static esp_err_t send_message(httpd_req_t *req, const char *title, const char *text)
{
    page_start(req, title);
    send(req, "<h1>");
    send_escaped(req, title);
    send(req, "</h1><p>");
    send_escaped(req, text);
    send(req, "</p>");
    return page_end(req);
}

/* --- Handlers ------------------------------------------------------------ */

static esp_err_t get_page(httpd_req_t *req)
{
    char host[64] = "";
    httpd_req_get_hdr_value_str(req, "Host", host, sizeof host);
    ESP_LOGI(TAG, "page requested as http://%s/", host);
    return send_form(req, NULL, 0);
}

static esp_err_t get_scan(httpd_req_t *req)
{
    setup_rescan();
    httpd_resp_set_status(req, "303 See Other");
    httpd_resp_set_hdr(req, "Location", "/");
    return httpd_resp_send(req, NULL, 0);
}

/* The whole body into s_body, or false (and a response sent) if it is
 * missing or too long to be the page's form. */
static bool read_body(httpd_req_t *req)
{
    if (req->content_len > BODY_MAX) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "form too large");
        return false;
    }
    size_t received = 0;
    while (received < req->content_len) {
        int got = httpd_req_recv(req, s_body + received, req->content_len - received);
        if (got == HTTPD_SOCK_ERR_TIMEOUT) {
            continue;
        }
        if (got <= 0) {
            return false;
        }
        received += (size_t)got;
    }
    s_body[received] = '\0';
    return true;
}

static esp_err_t post_save(httpd_req_t *req)
{
    if (!read_body(req)) {
        return ESP_OK;
    }
    bp_settings_t next;
    bp_field_set_t invalid = 0;
    if (!bp_settings_apply_form(settings(), s_body, settings_camera_limits(), &next,
                                &invalid)) {
        ESP_LOGW(TAG, "settings refused: invalid field(s) 0x%03" PRIx32, invalid);
        httpd_resp_set_status(req, "400 Bad Request");
        return send_form(req, s_body, invalid);
    }
    if (settings_save(&next) != ESP_OK) {
        httpd_resp_set_status(req, "500 Internal Server Error");
        return send_message(req, "Not saved",
                            "The device could not store the settings. Nothing "
                            "changed; try again.");
    }
    esp_err_t err = send_message(req, "Saved",
                                 "The device is restarting with the new settings. "
                                 "This network is closing; your phone will go back "
                                 "to its usual one.");
    setup_done();
    return err;
}

static esp_err_t post_reset(httpd_req_t *req)
{
    if (settings_erase() != ESP_OK) {
        httpd_resp_set_status(req, "500 Internal Server Error");
        return send_message(req, "Not reset",
                            "The device could not erase its settings. Nothing "
                            "changed; try again.");
    }
    esp_err_t err = send_message(req, "Reset",
                                 "Everything saved on the device is forgotten. It is "
                                 "restarting with the values it was built with.");
    setup_done();
    return err;
}

/* Up to `want` bytes of the body into `into`; false if the connection
 * fails or the body ends early. */
static bool receive(httpd_req_t *req, uint8_t *into, size_t want)
{
    size_t have = 0;
    while (have < want) {
        int got = httpd_req_recv(req, (char *)into + have, want - have);
        if (got == HTTPD_SOCK_ERR_TIMEOUT) {
            continue;
        }
        if (got <= 0) {
            return false;
        }
        have += (size_t)got;
    }
    return true;
}

/* Reads and drops what is left of the body. A browser still sending a
 * file when the answer comes reports a reset connection, not the answer,
 * so the reason would never be seen. */
static void drain(httpd_req_t *req, size_t remaining)
{
    while (remaining > 0) {
        size_t want = remaining < sizeof s_chunk ? remaining : sizeof s_chunk;
        int got = httpd_req_recv(req, (char *)s_chunk, want);
        if (got == HTTPD_SOCK_ERR_TIMEOUT) {
            continue;
        }
        if (got <= 0) {
            return;
        }
        remaining -= (size_t)got;
    }
}

static esp_err_t refuse_update(httpd_req_t *req, size_t remaining, const char *why)
{
    drain(req, remaining);
    httpd_resp_set_status(req, "400 Bad Request");
    return send_message(req, "Firmware not installed", why);
}

static esp_err_t post_update(httpd_req_t *req)
{
    const size_t total = req->content_len;
    const char *incomplete = "The upload did not arrive whole: nothing was changed.";
    if (total < BP_IMAGE_HEAD_SIZE) {
        return refuse_update(req, total,
                             bp_image_check_reason(BP_IMAGE_NOT_FIRMWARE,
                                                   BORESIGHT_IS_EMULATOR));
    }
    size_t received = total < sizeof s_chunk ? total : sizeof s_chunk;
    if (!receive(req, s_chunk, received)) {
        return refuse_update(req, 0, incomplete);
    }
    const char *reason = NULL;
    if (ota_upload_begin(s_chunk, received, total, &reason) != ESP_OK) {
        return refuse_update(req, total - received, reason);
    }
    esp_err_t err = ota_upload_write(s_chunk, received);
    while (err == ESP_OK && received < total) {
        size_t want = total - received < sizeof s_chunk ? total - received
                                                       : sizeof s_chunk;
        if (!receive(req, s_chunk, want)) {
            ota_upload_abort();
            return refuse_update(req, 0, incomplete);
        }
        err = ota_upload_write(s_chunk, want);
        received += want;
    }
    if (err != ESP_OK) {
        ota_upload_abort();
        return refuse_update(req, total - received,
                             "The image could not be written: nothing was changed.");
    }
    if (ota_upload_finish(&reason) != ESP_OK) {
        return refuse_update(req, 0, reason);
    }
    char text[96];
    snprintf(text, sizeof text,
             "Installed %s. The device is restarting into it; settings are kept.",
             ota_upload_version());
    err = send_message(req, "Firmware installed", text);
    setup_done();
    return err;
}

/* Any other path, including the phones' sign-in checks: off to the page. */
static esp_err_t redirect_home(httpd_req_t *req, httpd_err_code_t error)
{
    (void)error;
    /* Logged: a phone's sign-in check arrives here, and whether it does
     * at all is what to know when the prompt does not appear. */
    char host[64] = "";
    httpd_req_get_hdr_value_str(req, "Host", host, sizeof host);
    ESP_LOGI(TAG, "%s http://%s%s: redirected to the page",
             http_method_str((enum http_method)req->method), host, req->uri);
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", s_home);
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, NULL, 0);
}

esp_err_t setup_http_start(const char *home)
{
    s_home = home;
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.stack_size = 8192;
    /* Phones open several connections for their sign-in checks; the
     * oldest is closed rather than a new one refused. */
    config.lru_purge_enable = true;
    esp_err_t err = httpd_start(&s_server, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "page server did not start: %s", esp_err_to_name(err));
        return err;
    }
    const httpd_uri_t routes[] = {
        {.uri = "/", .method = HTTP_GET, .handler = get_page},
        {.uri = "/scan", .method = HTTP_GET, .handler = get_scan},
        {.uri = "/save", .method = HTTP_POST, .handler = post_save},
        {.uri = "/reset", .method = HTTP_POST, .handler = post_reset},
        {.uri = "/update", .method = HTTP_POST, .handler = post_update},
    };
    for (size_t i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        httpd_register_uri_handler(s_server, &routes[i]);
    }
    httpd_register_err_handler(s_server, HTTPD_404_NOT_FOUND, redirect_home);
    ESP_LOGI(TAG, "setup page served on port %d", config.server_port);
    return ESP_OK;
}

void setup_http_stop(void)
{
    if (s_server != NULL) {
        httpd_stop(s_server);
        s_server = NULL;
    }
}
