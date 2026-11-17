# Boresight ESP32-CAM firmware. ESP-IDF v5.x:
#
#   idf.py set-target esp32
#   idf.py menuconfig        # "Boresight camera" menu
#   idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)

# Reported to the server in `hello`, and in the boot log.
set(PROJECT_VER "0.1.0")

# The emulator profile (tools/idf.sh emulator) adds sdkconfig.emulator to
# the defaults. Its version says so in the image itself, so a firmware
# upload can tell an emulator image from a board's before installing it.
# The configuration is not read yet at this point; its file list is.
if(SDKCONFIG_DEFAULTS MATCHES "sdkconfig\\.emulator")
    set(PROJECT_VER "${PROJECT_VER}+emulator")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(boresight-cam)
