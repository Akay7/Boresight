# Sources differ by build profile; requirements cannot (ESP-IDF resolves
# them before the configuration is read), so both profiles' are listed.
if(CONFIG_BORESIGHT_EMULATOR)
    # QEMU: emulated Ethernet for Wi-Fi, recorded frames for the sensor,
    # console commands for the button pins.
    set(profile_sources "net_openeth.c" "camera_fake.c" "console.c")
else()
    set(profile_sources "wifi.c" "camera.c")
endif()

idf_component_register(
    SRCS
        "main.c"
        "link.c"
        "buttons.c"
        "status_led.c"
        ${profile_sources}
    INCLUDE_DIRS "."
    REQUIRES
        boresight_proto
        driver
        esp_app_format
        esp_eth
        esp_event
        esp_netif
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

# The emulator's camera: frames of the project's Blender scene rendered as
# the ESP32-CAM sees it. Must match the count in camera_fake.c.
if(CONFIG_BORESIGHT_EMULATOR)
    set(fixture_dir "${COMPONENT_DIR}/../../../tests/fixtures/esp32cam_video")
    foreach(n RANGE 1 8)
        set(frame "${fixture_dir}/frame_000${n}.jpg")
        if(NOT EXISTS "${frame}")
            message(FATAL_ERROR
                "Emulator frame missing: ${frame}\n"
                "Render it with `uv run python -m "
                "tests.generate_synthetic_video_fixture --profile esp32cam`.")
        endif()
        # A fixture that was never fetched from Git LFS is a small text
        # pointer; embedded, it would fail only at runtime, as a frame the
        # server cannot decode. A configure dependency, so a frame that
        # changes after the first configure is checked again rather than
        # embedded as it is.
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${frame}")
        file(READ "${frame}" magic LIMIT 2 HEX)
        if(NOT magic STREQUAL "ffd8")
            message(FATAL_ERROR
                "${frame} is not a JPEG -- probably a Git LFS pointer that "
                "was never fetched. Run `git lfs pull`.")
        endif()
        target_add_binary_data(${COMPONENT_LIB} "${frame}" BINARY)
    endforeach()
endif()
