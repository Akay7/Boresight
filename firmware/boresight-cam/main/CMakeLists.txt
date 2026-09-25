idf_component_register(
    SRCS
        "main.c"
        "wifi.c"
        "camera.c"
        "link.c"
        "buttons.c"
        "status_led.c"
    INCLUDE_DIRS "."
    REQUIRES
        boresight_proto
        driver
        esp_event
        esp_timer
        esp_wifi
        json
        mbedtls
        nvs_flash
)

# Under TLS the server's own certificate is the only trust anchor, so it
# is baked into the image. Checked here rather than at boot: a firmware
# that cannot possibly connect should not build.
if(CONFIG_BORESIGHT_TLS)
    if(NOT EXISTS "${COMPONENT_DIR}/server_cert.pem")
        message(FATAL_ERROR
            "CONFIG_BORESIGHT_TLS is on but main/server_cert.pem is missing.\n"
            "Copy the server's certificate there -- by default "
            ".boresight/cert.pem in the directory the server runs from.")
    endif()
    target_add_binary_data(${COMPONENT_LIB} "server_cert.pem" TEXT)
endif()
