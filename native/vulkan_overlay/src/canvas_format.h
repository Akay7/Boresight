/* The `.bsov` canvas handoff format.
 *
 * This is the C side of a contract documented in full, field-for-field,
 * in `src/boresight/overlay/canvas_format.py`'s module docstring --
 * that Python module is what actually writes the file; this header
 * only reads it back. `tests/test_overlay_vulkan_canvas.py` round-trips
 * a known input through the Python writer and asserts the bytes match
 * what this header's layout implies, so the two cannot silently drift.
 *
 * Layout, little-endian throughout (the only endianness either side
 * runs on):
 *
 *   header   4 bytes  magic       "BSOV"
 *            u32      version     1
 *            u32      width       canvas width, pixels
 *            u32      height      canvas height, pixels
 *            u32      rect_count  number of rectangles that follow
 *            u32      reserved    0
 *
 *   rects    rect_count * (u32 x, u32 y, u32 w, u32 h)
 *
 *   pixels   width * height bytes, row-major, one grayscale byte per
 *            pixel -- exactly `render_overlay`'s canvas, byte for byte.
 */

#ifndef BORESIGHT_CANVAS_FORMAT_H
#define BORESIGHT_CANVAS_FORMAT_H

#include <stddef.h>
#include <stdint.h>

#define BSOV_MAGIC "BSOV"
#define BSOV_VERSION 1u

/* Sanity bounds checked before anything is allocated -- mirrored as
 * MAX_DIMENSION / MAX_RECTS in canvas_format.py's `unpack`. 16384 is
 * the common maxImageDimension2D and above any real display; it also
 * keeps the layer's 4-byte-per-texel expansion (width*height*4) far
 * from overflowing size_t. `render_overlay` produces tens of rects. */
#define BSOV_MAX_DIMENSION 16384u
#define BSOV_MAX_RECTS 4096u

#pragma pack(push, 1)
typedef struct {
    char magic[4];
    uint32_t version;
    uint32_t width;
    uint32_t height;
    uint32_t rect_count;
    uint32_t reserved;
} bsov_header_t;

typedef struct {
    uint32_t x, y, w, h;
} bsov_rect_t;
#pragma pack(pop)

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t rect_count;
    bsov_rect_t *rects; /* rect_count entries, owned, malloc'd */
    uint8_t *pixels;    /* width*height bytes, owned, malloc'd, grayscale */
} bsov_canvas_t;

/* Reads and validates a `.bsov` file from `path`, filling `out` on
 * success. Returns 0 on success; returns nonzero on any failure
 * (missing file, bad magic/version, width/height/rect_count out of
 * bounds, a file shorter than its header declares, or any rect that is
 * empty or not entirely inside the canvas) and leaves `out` untouched.
 * On success every rect satisfies 0 < w, 0 < h, x + w <= width and
 * y + h <= height, so callers may turn them into image copy regions
 * without further checks. Every failure is treated identically by callers: "no
 * canvas for this swapchain," never a crash -- see the "presented
 * frames remain valid" requirement this exists to uphold. */
int bsov_load(const char *path, bsov_canvas_t *out);

/* Returns 1 if `canvas` may be drawn into an image of `width` x
 * `height` -- the swapchain extent -- and 0 otherwise. It must be
 * exactly that size (a canvas for any other size is a stale layout,
 * and neither clamped nor scaled), hold pixels, and have every rect
 * inside the extent by the same overflow-free rule `bsov_load` applies
 * against the canvas. That last check is redundant after `bsov_load`
 * and deliberate: this states, in terms of the image being written,
 * the one property that makes each rect a valid vkCmdCopyImage region,
 * so it holds for any canvas handed to it. NULL returns 0. */
int bsov_fits_extent(const bsov_canvas_t *canvas, uint32_t width, uint32_t height);

/* Frees the buffers `bsov_load` allocated. Safe to call on a
 * zero-initialized (never-loaded) canvas. */
void bsov_free(bsov_canvas_t *canvas);

#endif /* BORESIGHT_CANVAS_FORMAT_H */
