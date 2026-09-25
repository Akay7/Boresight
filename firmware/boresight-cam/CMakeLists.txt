# Boresight ESP32-CAM firmware. ESP-IDF v5.x:
#
#   idf.py set-target esp32
#   idf.py menuconfig        # "Boresight camera" menu
#   idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)

# Reported to the server in `hello`, and in the boot log.
set(PROJECT_VER "0.1.0")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(boresight-cam)
