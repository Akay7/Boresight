/*
 * Host tests for setup mode's platform-independent half: settings, the
 * posted form, HTML escaping, the setup network's name lookups and the
 * discovered server's TLS check.
 */
#include "boresight_setup.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;

#define CHECK(condition)                                                    \
    do {                                                                    \
        if (!(condition)) {                                                 \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, \
                    #condition);                                            \
            failures++;                                                     \
        }                                                                   \
    } while (0)

/* The ranges menuconfig allows (main/Kconfig.projbuild). */
static const bp_camera_limits_t LIMITS = {
    .jpeg_quality = {4, 63},
    .max_fps = {1, 30},
    .exposure = {0, 1200},
    .gain = {0, 30},
};

/* What a build would supply: the Kconfig defaults, with a network set. */
static bp_settings_t defaults(void)
{
    bp_settings_t s;
    memset(&s, 0, sizeof s);
    strcpy(s.ssid, "Home");
    strcpy(s.password, "old-password");
    strcpy(s.host, "192.168.1.40");
    s.port = 7331;
    strcpy(s.token, "old-token");
    s.resolution = BP_RES_XGA;
    s.jpeg_quality = 12;
    s.max_fps = 20;
    s.exposure = 300;
    s.gain = 0;
    return s;
}

/* A complete form as the page posts it, secrets left empty. */
#define FULL_FORM                                                        \
    "ssid=Home&password=&host=192.168.1.40&port=7331&token="           \
    "&resolution=1024x768&jpeg_quality=12&max_fps=20&exposure=300&gain=0"

static bool has(bp_field_set_t set, bp_field_t field)
{
    return (set & (1u << field)) != 0;
}

/* --- Settings ------------------------------------------------------------ */

static void test_settings_built_from_defaults_round_trip_through_the_form(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0xFFFFFFFFu;

    CHECK(bp_settings_apply_form(&current, FULL_FORM, &LIMITS, &out, &invalid));
    CHECK(invalid == 0);
    CHECK(memcmp(&out, &current, sizeof out) == 0);
}

static void test_resolution_names_and_sizes(void)
{
    int width = 0;
    int height = 0;
    bp_resolution_size(BP_RES_SVGA, &width, &height);
    CHECK(width == 800 && height == 600);
    CHECK(strcmp(bp_resolution_name(BP_RES_HD), "1280x720") == 0);
    CHECK(strcmp(bp_field_name(BP_FIELD_JPEG_QUALITY), "jpeg_quality") == 0);
}

/* --- Form decoding ------------------------------------------------------- */

static void test_form_decoding(void)
{
    char out[32];

    CHECK(bp_form_decode("My+Home", 7, out, sizeof out) == 7);
    CHECK(strcmp(out, "My Home") == 0);

    CHECK(bp_form_decode("a%26b%3Dc%2b", 12, out, sizeof out) == 6);
    CHECK(strcmp(out, "a&b=c+") == 0);

    /* UTF-8 survives byte for byte. */
    CHECK(bp_form_decode("caf%C3%A9", 9, out, sizeof out) == 5);
    CHECK(strcmp(out, "caf\xC3\xA9") == 0);
}

static void test_form_decoding_refuses_what_is_malformed_or_too_long(void)
{
    char out[8];

    CHECK(bp_form_decode("%G1", 3, out, sizeof out) == -1);
    CHECK(bp_form_decode("abc%4", 5, out, sizeof out) == -1);
    CHECK(bp_form_decode("abc%", 4, out, sizeof out) == -1);
    CHECK(bp_form_decode("nul%00here", 10, out, sizeof out) == -1);
    /* Seven characters fit with the NUL; eight do not. */
    CHECK(bp_form_decode("1234567", 7, out, sizeof out) == 7);
    CHECK(bp_form_decode("12345678", 8, out, sizeof out) == -1);
}

static void test_form_fields_are_found_by_name(void)
{
    char out[16];

    CHECK(bp_form_get("ssid=Home&port=80", "port", out, sizeof out) == 2);
    CHECK(strcmp(out, "80") == 0);
    CHECK(bp_form_get("ssid=Home&port=80", "host", out, sizeof out) == -1);
    /* A prefix of another field's name is not that field. */
    CHECK(bp_form_get("hostname=x&host=y", "host", out, sizeof out) == 1);
    CHECK(strcmp(out, "y") == 0);
    CHECK(bp_form_get("token=", "token", out, sizeof out) == 0);
    CHECK(bp_form_get("token", "token", out, sizeof out) == 0);
    CHECK(bp_form_get("port=%ZZ", "port", out, sizeof out) == -2);
}

/* --- Applying a form ----------------------------------------------------- */

static void test_an_out_of_range_port_changes_nothing(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out = defaults();
    strcpy(out.ssid, "untouched");
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current,
                                  "ssid=Home&port=70000&token=new-token&host=",
                                  &LIMITS, &out, &invalid));
    CHECK(has(invalid, BP_FIELD_PORT));
    CHECK(!has(invalid, BP_FIELD_TOKEN));
    /* Not even the valid token was taken. */
    CHECK(strcmp(out.ssid, "untouched") == 0);
    CHECK(strcmp(out.token, "old-token") == 0);
}

static void test_a_seven_character_password_is_refused(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current, "ssid=Home&password=1234567", &LIMITS,
                                  &out, &invalid));
    CHECK(invalid == (1u << BP_FIELD_PASSWORD));

    /* 8 and 63 are fine; 64 is a raw key, not a passphrase. */
    CHECK(bp_password_valid("12345678"));
    CHECK(bp_password_valid(
        "123456789012345678901234567890123456789012345678901234567890123"));
    CHECK(!bp_password_valid(
        "1234567890123456789012345678901234567890123456789012345678901234"));
}

static void test_an_invalid_host_is_refused(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current, "ssid=Home&host=192.168.1", &LIMITS, &out,
                                  &invalid));
    CHECK(invalid == (1u << BP_FIELD_HOST));

    CHECK(bp_host_valid(""));
    CHECK(bp_host_valid("192.168.1.40"));
    CHECK(bp_host_valid("gaming-pc.local"));
    CHECK(!bp_host_valid("256.1.1.1"));
    CHECK(!bp_host_valid("1.2.3.4.5"));
    CHECK(!bp_host_valid("-pc.local"));
    CHECK(!bp_host_valid("pc-.local"));
    CHECK(!bp_host_valid("pc..local"));
    CHECK(!bp_host_valid("pc local"));
    CHECK(!bp_host_valid("http://pc"));
}

static void test_an_out_of_range_camera_value_is_refused(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current,
                                  "ssid=Home&jpeg_quality=3&exposure=1201&gain=-1"
                                  "&max_fps=30&resolution=999x1",
                                  &LIMITS, &out, &invalid));
    CHECK(has(invalid, BP_FIELD_JPEG_QUALITY));
    CHECK(has(invalid, BP_FIELD_EXPOSURE));
    CHECK(has(invalid, BP_FIELD_GAIN));
    CHECK(has(invalid, BP_FIELD_RESOLUTION));
    CHECK(!has(invalid, BP_FIELD_MAX_FPS));
}

static void test_valid_values_are_taken(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(bp_settings_apply_form(&current,
                                  "ssid=Office+Wi-Fi&password=12345678&host=&port=9100"
                                  "&token=abc_DEF-1.2~&resolution=800x600"
                                  "&jpeg_quality=10&max_fps=15&exposure=500&gain=4",
                                  &LIMITS, &out, &invalid));
    CHECK(invalid == 0);
    CHECK(strcmp(out.ssid, "Office Wi-Fi") == 0);
    CHECK(strcmp(out.password, "12345678") == 0);
    CHECK(out.host[0] == '\0');
    CHECK(out.port == 9100);
    CHECK(strcmp(out.token, "abc_DEF-1.2~") == 0);
    CHECK(out.resolution == BP_RES_SVGA);
    CHECK(out.jpeg_quality == 10 && out.max_fps == 15);
    CHECK(out.exposure == 500 && out.gain == 4);
}

static void test_the_network_name_is_required(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current, "port=7331", &LIMITS, &out, &invalid));
    CHECK(invalid == (1u << BP_FIELD_SSID));
    CHECK(!bp_settings_apply_form(&current, "ssid=", &LIMITS, &out, &invalid));
    CHECK(!bp_settings_apply_form(&current,
                                  "ssid=123456789012345678901234567890123", &LIMITS,
                                  &out, &invalid));
    CHECK(invalid == (1u << BP_FIELD_SSID));
}

static void test_empty_secrets_keep_the_stored_ones(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(bp_settings_apply_form(&current, "ssid=Home&port=9100&password=&token=",
                                  &LIMITS, &out, &invalid));
    CHECK(strcmp(out.password, "old-password") == 0);
    CHECK(strcmp(out.token, "old-token") == 0);
    CHECK(out.port == 9100);
}

static void test_the_clear_boxes_remove_secrets(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(bp_settings_apply_form(&current,
                                  "ssid=Open+Cafe&password=&clear_password=1&token="
                                  "&clear_token=on",
                                  &LIMITS, &out, &invalid));
    CHECK(out.password[0] == '\0');
    CHECK(out.token[0] == '\0');

    /* A typed value wins over its clear box. */
    CHECK(bp_settings_apply_form(&current,
                                  "ssid=Home&token=fresh&clear_token=1", &LIMITS, &out,
                                  &invalid));
    CHECK(strcmp(out.token, "fresh") == 0);
}

static void test_a_token_that_would_break_the_url_is_refused(void)
{
    const bp_settings_t current = defaults();
    bp_settings_t out;
    bp_field_set_t invalid = 0;

    CHECK(!bp_settings_apply_form(&current, "ssid=Home&token=a%26b", &LIMITS, &out,
                                  &invalid));
    CHECK(invalid == (1u << BP_FIELD_TOKEN));
    CHECK(!bp_token_valid("has space"));
    CHECK(!bp_token_valid("x#y"));
    CHECK(bp_token_valid("xK3f-_.~"));
}

/* --- HTML ---------------------------------------------------------------- */

static void test_a_hostile_network_name_is_escaped(void)
{
    char out[128];

    CHECK(bp_html_escape("<script>alert('x')</script>&\"", out, sizeof out) > 0);
    CHECK(strcmp(out, "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;&amp;&quot;") ==
          0);
    CHECK(bp_html_escape("plain", out, sizeof out) == 5);
    CHECK(strcmp(out, "plain") == 0);
    /* An escape that would not fit whole is refused, not cut. */
    CHECK(bp_html_escape("a<", out, 5) == -1);
    CHECK(bp_html_escape("a<", out, 6) == 5);
}

/* --- DNS ----------------------------------------------------------------- */

static const uint8_t SETUP_IP[4] = {192, 168, 4, 1};

/* An A query for connectivitycheck.gstatic.com, the name Android checks,
 * with recursion desired and an EDNS0 OPT record, as Android's resolver
 * sends it. Built by hand per RFC 1035 and RFC 6891. */
static const uint8_t ANDROID_QUERY[] = {
    0x1a, 0x2b, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
    17, 'c', 'o', 'n', 'n', 'e', 'c', 't', 'i', 'v', 'i', 't', 'y', 'c', 'h', 'e',
    'c', 'k', 7, 'g', 's', 't', 'a', 't', 'i', 'c', 3, 'c', 'o', 'm', 0,
    0x00, 0x01, 0x00, 0x01,
    /* OPT: root name, type 41, UDP size 1232, no flags, no data. */
    0x00, 0x00, 0x29, 0x04, 0xd0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

/* captive.apple.com, as iOS asks for it: an A query and an AAAA query. */
static const uint8_t IOS_A_QUERY[] = {
    0x55, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    7, 'c', 'a', 'p', 't', 'i', 'v', 'e', 5, 'a', 'p', 'p', 'l', 'e', 3, 'c', 'o',
    'm', 0, 0x00, 0x01, 0x00, 0x01,
};
static const uint8_t IOS_AAAA_QUERY[] = {
    0x55, 0x02, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    7, 'c', 'a', 'p', 't', 'i', 'v', 'e', 5, 'a', 'p', 'p', 'l', 'e', 3, 'c', 'o',
    'm', 0, 0x00, 0x1c, 0x00, 0x01,
};

static void test_an_a_query_is_answered_with_the_setup_address(void)
{
    uint8_t reply[512];
    const size_t question_end = sizeof ANDROID_QUERY - 11; /* before the OPT */

    int length = bp_dns_answer(ANDROID_QUERY, sizeof ANDROID_QUERY, SETUP_IP, reply,
                               sizeof reply);

    CHECK(length == (int)(question_end + 16));
    CHECK(reply[0] == 0x1a && reply[1] == 0x2b); /* the query's id */
    CHECK(reply[2] == 0x85);                     /* response, authoritative, RD */
    CHECK(reply[3] == 0x00);                     /* NOERROR */
    CHECK(reply[5] == 1 && reply[7] == 1);       /* one question, one answer */
    CHECK(reply[9] == 0 && reply[11] == 0);      /* the OPT is not echoed */
    CHECK(memcmp(reply + 12, ANDROID_QUERY + 12, question_end - 12) == 0);
    const uint8_t *answer = reply + question_end;
    const uint8_t expected[16] = {0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0, 0,
                                  0,    60,   0,    4,    192,  168,  4, 1};
    CHECK(memcmp(answer, expected, sizeof expected) == 0);

    length = bp_dns_answer(IOS_A_QUERY, sizeof IOS_A_QUERY, SETUP_IP, reply,
                           sizeof reply);
    CHECK(length == (int)sizeof IOS_A_QUERY + 16);
    CHECK(memcmp(reply + length - 4, SETUP_IP, 4) == 0);
}

static void test_other_query_types_get_no_answer(void)
{
    uint8_t reply[512];

    int length = bp_dns_answer(IOS_AAAA_QUERY, sizeof IOS_AAAA_QUERY, SETUP_IP, reply,
                               sizeof reply);

    CHECK(length == (int)sizeof IOS_AAAA_QUERY);
    CHECK(reply[2] == 0x85 && reply[3] == 0x00);
    CHECK(reply[7] == 0); /* no answers */
}

static void test_packets_that_are_not_one_plain_query_are_ignored(void)
{
    uint8_t reply[512];
    uint8_t packet[sizeof IOS_A_QUERY];

    /* Truncated: in the header, in the name, and before type and class. */
    CHECK(bp_dns_answer(IOS_A_QUERY, 11, SETUP_IP, reply, sizeof reply) == -1);
    CHECK(bp_dns_answer(IOS_A_QUERY, 20, SETUP_IP, reply, sizeof reply) == -1);
    CHECK(bp_dns_answer(IOS_A_QUERY, sizeof IOS_A_QUERY - 2, SETUP_IP, reply,
                        sizeof reply) == -1);

    /* A response, not a query. */
    memcpy(packet, IOS_A_QUERY, sizeof packet);
    packet[2] |= 0x80;
    CHECK(bp_dns_answer(packet, sizeof packet, SETUP_IP, reply, sizeof reply) == -1);

    /* Not a standard query (opcode 2, status). */
    memcpy(packet, IOS_A_QUERY, sizeof packet);
    packet[2] = 0x10;
    CHECK(bp_dns_answer(packet, sizeof packet, SETUP_IP, reply, sizeof reply) == -1);

    /* Two questions. */
    memcpy(packet, IOS_A_QUERY, sizeof packet);
    packet[5] = 2;
    CHECK(bp_dns_answer(packet, sizeof packet, SETUP_IP, reply, sizeof reply) == -1);

    /* A compression pointer where a label should be. */
    memcpy(packet, IOS_A_QUERY, sizeof packet);
    packet[12] = 0xC0;
    CHECK(bp_dns_answer(packet, sizeof packet, SETUP_IP, reply, sizeof reply) == -1);

    /* A reply that would not fit. */
    CHECK(bp_dns_answer(IOS_A_QUERY, sizeof IOS_A_QUERY, SETUP_IP, reply,
                        sizeof IOS_A_QUERY) == -1);
}

/* --- Firmware images ----------------------------------------------------- */

static size_t read_fixture(const char *name, uint8_t *out, size_t size)
{
    char path[512];
    snprintf(path, sizeof path, "%s/%s", FIXTURE_DIR, name);
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "missing fixture %s\n", path);
        failures++;
        return 0;
    }
    size_t length = fread(out, 1, size, file);
    fclose(file);
    return length;
}

static void test_a_device_image_is_accepted_by_a_board_only(void)
{
    uint8_t head[256];
    char version[33];
    size_t length = read_fixture("device_image_head.bin", head, sizeof head);

    CHECK(bp_app_image_check(head, length, false, version, sizeof version) ==
          BP_IMAGE_OK);
    CHECK(strcmp(version, "0.1.0") == 0);
    CHECK(bp_app_image_check(head, length, true, version, sizeof version) ==
          BP_IMAGE_WRONG_KIND);
    CHECK(strstr(bp_image_check_reason(BP_IMAGE_WRONG_KIND, true), "board") != NULL);
}

static void test_an_emulator_image_is_accepted_by_the_emulator_only(void)
{
    uint8_t head[256];
    char version[33];
    size_t length = read_fixture("emulator_image_head.bin", head, sizeof head);

    CHECK(bp_app_image_check(head, length, true, version, sizeof version) ==
          BP_IMAGE_OK);
    CHECK(strcmp(version, "0.1.0+emulator") == 0);
    CHECK(bp_app_image_check(head, length, false, version, sizeof version) ==
          BP_IMAGE_WRONG_KIND);
    CHECK(strstr(bp_image_check_reason(BP_IMAGE_WRONG_KIND, false), "emulator") !=
          NULL);
}

static void test_what_is_not_a_boresight_firmware_is_refused(void)
{
    uint8_t head[256];
    char version[33];
    size_t length = read_fixture("device_image_head.bin", head, sizeof head);

    /* Arbitrary bytes, and a JPEG. */
    uint8_t noise[256];
    for (size_t i = 0; i < sizeof noise; i++) {
        noise[i] = (uint8_t)(i * 37u + 11u);
    }
    CHECK(bp_app_image_check(noise, sizeof noise, false, version, sizeof version) ==
          BP_IMAGE_NOT_FIRMWARE);
    const uint8_t jpeg[BP_IMAGE_HEAD_SIZE] = {0xFF, 0xD8, 0xFF, 0xE0};
    CHECK(bp_app_image_check(jpeg, sizeof jpeg, false, NULL, 0) ==
          BP_IMAGE_NOT_FIRMWARE);

    /* Too short to hold the descriptor. */
    CHECK(bp_app_image_check(head, BP_IMAGE_HEAD_SIZE - 1, false, version,
                             sizeof version) == BP_IMAGE_NOT_FIRMWARE);

    /* An ESP-IDF image of another project. */
    uint8_t other[256];
    memcpy(other, head, sizeof other);
    memset(other + 80, 0, 32);
    memcpy(other + 80, "esp32-blink", 11);
    CHECK(bp_app_image_check(other, length, false, version, sizeof version) ==
          BP_IMAGE_OTHER_PROJECT);

    /* The image magic right but no app descriptor: a bootloader, say. */
    uint8_t bare[256];
    memcpy(bare, head, sizeof bare);
    bare[32] = 0;
    CHECK(bp_app_image_check(bare, length, false, version, sizeof version) ==
          BP_IMAGE_NOT_FIRMWARE);
}

/* --- Discovery ----------------------------------------------------------- */

static void test_discovered_tls_must_match_the_build(void)
{
    CHECK(bp_discovery_tls_ok("0", false));
    CHECK(bp_discovery_tls_ok("1", true));
    CHECK(!bp_discovery_tls_ok("1", false));
    CHECK(!bp_discovery_tls_ok("0", true));
    CHECK(!bp_discovery_tls_ok(NULL, false));
    CHECK(!bp_discovery_tls_ok(NULL, true));
    CHECK(!bp_discovery_tls_ok("yes", true));
}

int main(void)
{
    test_settings_built_from_defaults_round_trip_through_the_form();
    test_resolution_names_and_sizes();
    test_form_decoding();
    test_form_decoding_refuses_what_is_malformed_or_too_long();
    test_form_fields_are_found_by_name();
    test_an_out_of_range_port_changes_nothing();
    test_a_seven_character_password_is_refused();
    test_an_invalid_host_is_refused();
    test_an_out_of_range_camera_value_is_refused();
    test_valid_values_are_taken();
    test_the_network_name_is_required();
    test_empty_secrets_keep_the_stored_ones();
    test_the_clear_boxes_remove_secrets();
    test_a_token_that_would_break_the_url_is_refused();
    test_a_hostile_network_name_is_escaped();
    test_an_a_query_is_answered_with_the_setup_address();
    test_other_query_types_get_no_answer();
    test_packets_that_are_not_one_plain_query_are_ignored();
    test_discovered_tls_must_match_the_build();
    test_a_device_image_is_accepted_by_a_board_only();
    test_an_emulator_image_is_accepted_by_the_emulator_only();
    test_what_is_not_a_boresight_firmware_is_refused();

    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("all setup checks passed\n");
    return 0;
}
