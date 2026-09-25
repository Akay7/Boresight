# Built two ways: as an ESP-IDF component for the firmware, and as a plain
# static library for the host tests in ../../test_host.
if(ESP_PLATFORM)
    idf_component_register(SRCS "boresight_proto.c" INCLUDE_DIRS "include")
else()
    add_library(boresight_proto STATIC boresight_proto.c)
    target_include_directories(boresight_proto PUBLIC include)
endif()
