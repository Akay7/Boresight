#include "canvas_format.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Every rect must be non-empty and lie wholly inside the canvas -- the
 * layer turns these straight into vkCmdCopyImage regions, where an
 * out-of-bounds one is undefined behaviour on the GPU. Written as
 * subtractions after bounding w/h, so `x + w` can never wrap. */
static int rect_is_valid(const bsov_rect_t *rect, uint32_t width, uint32_t height) {
    if (rect->w == 0 || rect->h == 0) {
        return 0;
    }
    if (rect->w > width || rect->h > height) {
        return 0;
    }
    return rect->x <= width - rect->w && rect->y <= height - rect->h;
}

/* Size of the open file, or -1 if it can't be determined. Leaves the
 * position where it was. */
static long file_size(FILE *f) {
    long here = ftell(f);
    if (here < 0 || fseek(f, 0, SEEK_END) != 0) {
        return -1;
    }
    long size = ftell(f);
    if (fseek(f, here, SEEK_SET) != 0) {
        return -1;
    }
    return size;
}

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
    if (header.width == 0 || header.height == 0 || header.width > BSOV_MAX_DIMENSION ||
        header.height > BSOV_MAX_DIMENSION || header.rect_count > BSOV_MAX_RECTS) {
        fclose(f);
        return 1;
    }

    /* Refuse a header that claims more data than the file holds before
     * allocating for it, rather than trusting the claim and letting
     * fread discover the truncation afterwards. All three terms are
     * bounded above, so this sum cannot overflow. Trailing bytes are
     * tolerated, as they always were. */
    size_t pixel_count = (size_t)header.width * (size_t)header.height;
    size_t needed = sizeof(header) + (size_t)header.rect_count * sizeof(bsov_rect_t) + pixel_count;
    long actual = file_size(f);
    if (actual < 0 || (unsigned long)actual < needed) {
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
        for (uint32_t i = 0; i < header.rect_count; i++) {
            if (!rect_is_valid(&rects[i], header.width, header.height)) {
                free(rects);
                fclose(f);
                return 1;
            }
        }
    }

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
