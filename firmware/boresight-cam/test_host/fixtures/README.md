# Image heads

The first 256 bytes of a device and an emulator build, for the firmware
image check (`bp_app_image_check`, test_setup.c). Cut after building both
profiles, from `firmware/boresight-cam`:

    head -c 256 build/boresight-cam.bin > test_host/fixtures/device_image_head.bin
    head -c 256 build-emulator/boresight-cam.bin > test_host/fixtures/emulator_image_head.bin

They hold the image header and the app descriptor (version 0.1.0 and
0.1.0+emulator, project boresight-cam). A rebuild changes the build time
and hash in them, not what the check reads, so they need no refreshing.
