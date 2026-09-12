cmake_minimum_required(VERSION 3.16)
project(boresight_vulkan_overlay C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# A single, predictable output directory regardless of generator, so the
# manifest we copy next to the built library (below) and the
# `VK_LAYER_PATH=<build dir>` instructions in README.md both point at
# one place.
if(NOT CMAKE_LIBRARY_OUTPUT_DIRECTORY)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
endif()

# Prefer a real Vulkan SDK/system install when one is present -- it
# wins by default in FindVulkan.cmake -- and fall back to fetching just
# the headers otherwise. This layer never links against the loader
# (see overlay_layer.c's file comment for why a Vulkan layer doesn't
# need to): only the headers matter for a clean build, which keeps
# "build this" possible on a machine that has the Vulkan *runtime*
# (libvulkan.so, needed to run any game at all) but not the
# *development* package -- exactly Boresight's own default state, and
# why this can't simply require `vulkan-devel` be preinstalled.
find_package(Vulkan QUIET)

if(Vulkan_FOUND)
    set(BORESIGHT_VULKAN_INCLUDE_DIR "${Vulkan_INCLUDE_DIRS}")
    message(STATUS "boresight_vulkan_overlay: using the system Vulkan SDK headers")
else()
    include(FetchContent)
    FetchContent_Declare(
        VulkanHeaders
        GIT_REPOSITORY https://github.com/KhronosGroup/Vulkan-Headers.git
        GIT_TAG v1.3.296
        GIT_SHALLOW TRUE
    )
    FetchContent_MakeAvailable(VulkanHeaders)
    set(BORESIGHT_VULKAN_INCLUDE_DIR "${vulkanheaders_SOURCE_DIR}/include")
    message(STATUS "boresight_vulkan_overlay: no system Vulkan SDK found, "
                    "fetched Vulkan-Headers v1.3.296 for the build")
endif()

find_package(Threads REQUIRED)

add_library(boresight_overlay SHARED
    src/canvas_format.c
    src/overlay_layer.c
)

target_include_directories(boresight_overlay PRIVATE
    ${BORESIGHT_VULKAN_INCLUDE_DIR}
    src
)

target_link_libraries(boresight_overlay PRIVATE Threads::Threads)
target_compile_options(boresight_overlay PRIVATE -Wall -Wextra)

set_target_properties(boresight_overlay PROPERTIES
    OUTPUT_NAME "boresight_overlay"
    PREFIX "lib"
)

# The explicit-layer manifest ships with a manifest-relative
# "./libboresight_overlay.so" library_path (loader-resolved relative to
# the JSON's own directory), so copying it beside the built library is
# enough -- no path substitution, no install step required for local
# testing: `VK_LAYER_PATH=<this output dir>` activates it.
add_custom_command(TARGET boresight_overlay POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        ${CMAKE_CURRENT_SOURCE_DIR}/resources/VkLayer_boresight_overlay.json
        $<TARGET_FILE_DIR:boresight_overlay>/VkLayer_boresight_overlay.json
    COMMENT "Copying the explicit-layer manifest next to libboresight_overlay.so"
)
