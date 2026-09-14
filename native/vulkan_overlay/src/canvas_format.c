#include "canvas_format.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int bsov_load(const char *path, bsov_canvas_t *out) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return 1;
    }

    bsov_header_t header;
    if (fread(&header, sizeof(header), 1, f) != 1) {
        fclose(f);
        return 1;
    }

    if (memcmp(header.magic, BSOV_MAGIC, sizeof(header.magic)) != 0) {
        fclose(f);
        return 1;
    }
    if (header.version != BSOV_VERSION) {
        fclose(f);
        return 1;
    }
    if (header.width == 0 || header.height == 0) {
        fclose(f);
        return 1;
    }

    bsov_rect_t *rects = NULL;
    if (header.rect_count > 0) {
        rects = calloc(header.rect_count, sizeof(bsov_rect_t));
        if (!rects) {
            fclose(f);
            return 1;
        }
        if (fread(rects, sizeof(bsov_rect_t), header.rect_count, f) != header.rect_count) {
            free(rects);
            fclose(f);
            return 1;
        }
    }

    size_t pixel_count = (size_t)header.width * (size_t)header.height;
    uint8_t *pixels = malloc(pixel_count);
    if (!pixels) {
        free(rects);
        fclose(f);
        return 1;
    }
    if (fread(pixels, 1, pixel_count, f) != pixel_count) {
        free(rects);
        free(pixels);
        fclose(f);
        return 1;
    }

    fclose(f);

    out->width = header.width;
    out->height = header.height;
    out->rect_count = header.rect_count;
    out->rects = rects;
    out->pixels = pixels;
    return 0;
}

void bsov_free(bsov_canvas_t *canvas) {
    if (!canvas) {
        return;
    }
    free(canvas->rects);
    free(canvas->pixels);
    canvas->rects = NULL;
    canvas->pixels = NULL;
    canvas->width = 0;
    canvas->height = 0;
    canvas->rect_count = 0;
}
