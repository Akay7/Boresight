/* bsov_load against valid and malformed `.bsov` files.
 *
 * With no arguments, runs the built-in cases (files written to a
 * mkdtemp directory under $TMPDIR, removed afterwards). With a path
 * argument, instead loads that file and exits 0 only if it is accepted
 * -- used to check a canvas written by the Python writer
 * (`canvas_format.write_file`) loads through the C reader too. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "canvas_format.h"

static int g_failures = 0;
static char g_dir[4096];

#define CHECK(cond, name)                                                  \
    do {                                                                   \
        if (!(cond)) {                                                     \
            fprintf(stderr, "FAIL: %s (%s:%d)\n", name, __FILE__, __LINE__); \
            g_failures++;                                                  \
        } else {                                                           \
            printf("ok: %s\n", name);                                      \
        }                                                                  \
    } while (0)

/* Writes a header, `rects`, and `pixel_bytes` bytes of pixels (which
 * may deliberately differ from width*height to test truncation). */
static void write_canvas(
    const char *path, uint32_t width, uint32_t height, uint32_t rect_count,
    const bsov_rect_t *rects, size_t rects_written, size_t pixel_bytes
) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        perror(path);
        exit(2);
    }
    bsov_header_t header = {{'B', 'S', 'O', 'V'}, BSOV_VERSION, width, height, rect_count, 0};
    fwrite(&header, sizeof(header), 1, f);
    if (rects_written) {
        fwrite(rects, sizeof(bsov_rect_t), rects_written, f);
    }
    for (size_t i = 0; i < pixel_bytes; i++) {
        fputc((int)(i & 0xff), f);
    }
    fclose(f);
}

/* Loads `path` and returns bsov_load's result, freeing on success and
 * checking the failure contract (`out` untouched) otherwise. */
static int load(const char *path) {
    bsov_canvas_t canvas = {0};
    int rc = bsov_load(path, &canvas);
    if (rc == 0) {
        bsov_free(&canvas);
    } else if (canvas.rects || canvas.pixels || canvas.width || canvas.height) {
        fprintf(stderr, "FAIL: %s: failed load modified `out`\n", path);
        g_failures++;
    }
    return rc;
}

static const char *case_path(const char *name) {
    static char path[4200];
    snprintf(path, sizeof(path), "%s/%s.bsov", g_dir, name);
    return path;
}

static void run_cases(void) {
    const uint32_t w = 64, h = 32;
    const size_t px = (size_t)w * h;
    const char *p;

    /* A valid canvas, including rects that touch the right/bottom edge
     * exactly -- the boundary must stay accepted. */
    bsov_rect_t valid[] = {{0, 0, 8, 8}, {56, 24, 8, 8}, {0, 0, w, h}};
    p = case_path("valid");
    write_canvas(p, w, h, 3, valid, 3, px);
    {
        bsov_canvas_t canvas = {0};
        int rc = bsov_load(p, &canvas);
        CHECK(rc == 0, "valid canvas loads");
        CHECK(canvas.width == w && canvas.height == h && canvas.rect_count == 3,
              "valid canvas header fields");
        CHECK(canvas.rects && canvas.rects[1].x == 56 && canvas.rects[1].h == 8,
              "valid canvas rects");
        CHECK(canvas.pixels && canvas.pixels[5] == 5 && canvas.pixels[px - 1] == (uint8_t)(px - 1),
              "valid canvas pixels");
        bsov_free(&canvas);
    }

    p = case_path("no_rects");
    write_canvas(p, w, h, 0, NULL, 0, px);
    CHECK(load(p) == 0, "zero rects is valid");

    p = case_path("trailing");
    write_canvas(p, w, h, 3, valid, 3, px + 17);
    CHECK(load(p) == 0, "trailing bytes are tolerated");

    bsov_rect_t right[] = {{57, 0, 8, 8}};
    p = case_path("past_right");
    write_canvas(p, w, h, 1, right, 1, px);
    CHECK(load(p) != 0, "rect past right edge rejected");

    bsov_rect_t bottom[] = {{0, 25, 8, 8}};
    p = case_path("past_bottom");
    write_canvas(p, w, h, 1, bottom, 1, px);
    CHECK(load(p) != 0, "rect past bottom edge rejected");

    bsov_rect_t origin_out[] = {{w, 0, 1, 1}};
    p = case_path("origin_out");
    write_canvas(p, w, h, 1, origin_out, 1, px);
    CHECK(load(p) != 0, "rect starting outside canvas rejected");

    /* x + w wraps to a small value in 32-bit arithmetic. */
    bsov_rect_t wrap_x[] = {{0xFFFFFFF8u, 0, 16, 8}};
    p = case_path("wrap_x");
    write_canvas(p, w, h, 1, wrap_x, 1, px);
    CHECK(load(p) != 0, "x + w overflow rejected");

    bsov_rect_t wrap_y[] = {{0, 0xFFFFFFFFu, 8, 1}};
    p = case_path("wrap_y");
    write_canvas(p, w, h, 1, wrap_y, 1, px);
    CHECK(load(p) != 0, "y + h overflow rejected");

    bsov_rect_t huge_w[] = {{0, 0, 0xFFFFFFFFu, 8}};
    p = case_path("huge_w");
    write_canvas(p, w, h, 1, huge_w, 1, px);
    CHECK(load(p) != 0, "w larger than canvas rejected");

    bsov_rect_t empty_w[] = {{0, 0, 0, 8}};
    p = case_path("empty_w");
    write_canvas(p, w, h, 1, empty_w, 1, px);
    CHECK(load(p) != 0, "zero-width rect rejected");

    bsov_rect_t empty_h[] = {{0, 0, 8, 0}};
    p = case_path("empty_h");
    write_canvas(p, w, h, 1, empty_h, 1, px);
    CHECK(load(p) != 0, "zero-height rect rejected");

    /* One bad rect among good ones still rejects the whole file. */
    bsov_rect_t mixed[] = {{0, 0, 8, 8}, {60, 0, 8, 8}};
    p = case_path("mixed");
    write_canvas(p, w, h, 2, mixed, 2, px);
    CHECK(load(p) != 0, "one bad rect rejects the file");

    p = case_path("truncated_rects");
    write_canvas(p, w, h, 3, valid, 2, 0);
    CHECK(load(p) != 0, "truncated rects rejected");

    p = case_path("truncated_pixels");
    write_canvas(p, w, h, 3, valid, 3, px - 1);
    CHECK(load(p) != 0, "truncated pixels rejected");

    p = case_path("header_only");
    write_canvas(p, w, h, 0, NULL, 0, 0);
    CHECK(load(p) != 0, "header with no pixels rejected");

    /* Claims far more rects than exist -- must be refused without
     * trying to allocate 64 GiB. */
    p = case_path("huge_rect_count");
    write_canvas(p, w, h, 0xFFFFFFFFu, valid, 3, px);
    CHECK(load(p) != 0, "huge rect_count rejected");

    p = case_path("over_max_rects");
    write_canvas(p, w, h, BSOV_MAX_RECTS + 1, NULL, 0, 0);
    CHECK(load(p) != 0, "rect_count over BSOV_MAX_RECTS rejected");

    p = case_path("huge_dims");
    write_canvas(p, 0xFFFFFFFFu, 0xFFFFFFFFu, 0, NULL, 0, px);
    CHECK(load(p) != 0, "huge width*height rejected");

    p = case_path("over_max_width");
    write_canvas(p, BSOV_MAX_DIMENSION + 1, 1, 0, NULL, 0, BSOV_MAX_DIMENSION + 1);
    CHECK(load(p) != 0, "width over BSOV_MAX_DIMENSION rejected");

    p = case_path("max_width");
    write_canvas(p, BSOV_MAX_DIMENSION, 1, 0, NULL, 0, BSOV_MAX_DIMENSION);
    CHECK(load(p) == 0, "width at BSOV_MAX_DIMENSION accepted");

    p = case_path("zero_width");
    write_canvas(p, 0, h, 0, NULL, 0, 0);
    CHECK(load(p) != 0, "zero width rejected");

    p = case_path("bad_magic");
    write_canvas(p, w, h, 0, NULL, 0, px);
    {
        FILE *f = fopen(p, "r+b");
        fwrite("NOPE", 1, 4, f);
        fclose(f);
    }
    CHECK(load(p) != 0, "bad magic rejected");

    p = case_path("short_header");
    {
        FILE *f = fopen(p, "wb");
        fwrite("BSOV", 1, 4, f);
        fclose(f);
    }
    CHECK(load(p) != 0, "short header rejected");

    CHECK(load(case_path("does_not_exist")) != 0, "missing file rejected");
}

static void remove_cases(void) {
    static const char *names[] = {
        "valid", "no_rects", "trailing", "past_right", "past_bottom", "origin_out",
        "wrap_x", "wrap_y", "huge_w", "empty_w", "empty_h", "mixed", "truncated_rects",
        "truncated_pixels", "header_only", "huge_rect_count", "over_max_rects", "huge_dims",
        "over_max_width", "max_width", "zero_width", "bad_magic", "short_header",
    };
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        unlink(case_path(names[i]));
    }
    rmdir(g_dir);
}

int main(int argc, char **argv) {
    if (argc > 1) {
        bsov_canvas_t canvas = {0};
        if (bsov_load(argv[1], &canvas) != 0) {
            fprintf(stderr, "rejected: %s\n", argv[1]);
            return 1;
        }
        printf("accepted: %s (%ux%u, %u rects)\n", argv[1], canvas.width, canvas.height,
               canvas.rect_count);
        bsov_free(&canvas);
        return 0;
    }

    const char *tmp = getenv("TMPDIR");
    snprintf(g_dir, sizeof(g_dir), "%s/bsov-test-XXXXXX", tmp && *tmp ? tmp : "/tmp");
    if (!mkdtemp(g_dir)) {
        perror("mkdtemp");
        return 2;
    }
    run_cases();
    remove_cases();

    if (g_failures) {
        fprintf(stderr, "%d failure(s)\n", g_failures);
        return 1;
    }
    return 0;
}
