# Host tests for the platform-independent firmware logic. No ESP-IDF, no
# board: plain CMake and the system C compiler.
#
#   cmake -S test_host -B build-host
#   cmake --build build-host
#   ctest --test-dir build-host --output-on-failure
cmake_minimum_required(VERSION 3.16)
project(boresight_cam_host_tests C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Werror)

add_subdirectory(../components/boresight_proto boresight_proto)

enable_testing()
add_executable(test_proto test_proto.c)
target_link_libraries(test_proto PRIVATE boresight_proto)
target_compile_definitions(test_proto PRIVATE
    FIXTURE_FRAME="${CMAKE_CURRENT_SOURCE_DIR}/../../../tests/fixtures/synthetic_video/frame_0001.jpg")
add_test(NAME boresight_proto COMMAND test_proto)
