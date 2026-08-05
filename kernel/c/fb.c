/* LionOS kernel C framebuffer drawing — compiled by build.rs and linked into
 * the kernel ELF alongside the Rust core. This is the "C half" of the
 * mixed-language graphics path: Rust validates the bootloader 0.11 framebuffer
 * descriptor (kernel/src/framebuffer.rs), then calls these routines to draw
 * into the mapped framebuffer.
 *
 * Constraints:
 *  - NO libc, NO headers, NO startup files. Types declared here.
 *  - position-dependent: compiled with -mcmodel=kernel -fno-pie to match the
 *    Rust kernel's static relocation model.
 *  - Every function bounds-checks x/y against width/height, so a malformed or
 *    hostile descriptor can never write outside the mapped framebuffer. The
 *    Rust validator additionally guarantees pitch >= width * bytes_per_pixel.
 */
typedef unsigned int  u32;
typedef unsigned char u8;

void lion_fb_clear(u8 *, u32, u32, u32, u32, u32);
void lion_fb_pixel(u8 *, u32, u32, u32, u32, u32, u32, u32);
void lion_fb_hline(u8 *, u32, u32, u32, u32, u32, u32, u32, u32);
void lion_fb_fill_rect(u8 *, u32, u32, u32, u32, u32, u32, u32, u32, u32);

/* Draw one pixel. offset = y*pitch + x*bpp_bytes; the caller has already
 * bounds-checked x/y, so the write stays inside the height*pitch buffer. */
static void put_pixel(u8 *base, u32 pitch, u32 bpp, u32 x, u32 y, u32 rgb) {
    u32 bpp_bytes = bpp / 8;
    u8 *p = base + (unsigned long)y * pitch + (unsigned long)x * bpp_bytes;
    if (bpp_bytes == 4) {
        p[0] = (u8)(rgb & 0xff);         /* B */
        p[1] = (u8)((rgb >> 8) & 0xff);  /* G */
        p[2] = (u8)((rgb >> 16) & 0xff); /* R */
        p[3] = 0xff;                     /* A */
    } else if (bpp_bytes == 3) {
        p[0] = (u8)(rgb & 0xff);
        p[1] = (u8)((rgb >> 8) & 0xff);
        p[2] = (u8)((rgb >> 16) & 0xff);
    } else {
        p[0] = (u8)(rgb & 0xff);
    }
}

/* Clear the whole framebuffer to `rgb`. */
void lion_fb_clear(u8 *base, u32 width, u32 height, u32 pitch, u32 bpp, u32 rgb) {
    lion_fb_fill_rect(base, width, height, pitch, bpp, 0, 0, width, height, rgb);
}

/* Fill the rectangle [x, x+rw) x [y, y+rh), clipped to the framebuffer. */
void lion_fb_fill_rect(u8 *base, u32 width, u32 height, u32 pitch, u32 bpp,
                       u32 x, u32 y, u32 rw, u32 rh, u32 rgb) {
    u32 bpp_bytes = bpp / 8;
    if (bpp_bytes != 1 && bpp_bytes != 3 && bpp_bytes != 4)
        return; /* unsupported pixel format — do nothing */
    u32 cy, cx;
    for (cy = 0; cy < rh; cy++) {
        u32 yy = y + cy;
        if (yy >= height) break;
        for (cx = 0; cx < rw; cx++) {
            u32 xx = x + cx;
            if (xx >= width) break;
            put_pixel(base, pitch, bpp, xx, yy, rgb);
        }
    }
}

/* Draw a horizontal line from x0 to x1 (inclusive) at row y, clipped. */
void lion_fb_hline(u8 *base, u32 width, u32 height, u32 pitch, u32 bpp,
                   u32 y, u32 x0, u32 x1, u32 rgb) {
    u32 bpp_bytes = bpp / 8;
    if (bpp_bytes != 1 && bpp_bytes != 3 && bpp_bytes != 4)
        return;
    if (y >= height)
        return;
    if (x0 > x1) {
        u32 t = x0; x0 = x1; x1 = t;
    }
    u32 x;
    for (x = x0; x <= x1; x++) {
        if (x >= width) break;
        put_pixel(base, pitch, bpp, x, y, rgb);
    }
}

/* Draw a single pixel, clipped. */
void lion_fb_pixel(u8 *base, u32 width, u32 height, u32 pitch, u32 bpp,
                   u32 x, u32 y, u32 rgb) {
    u32 bpp_bytes = bpp / 8;
    if (bpp_bytes != 1 && bpp_bytes != 3 && bpp_bytes != 4)
        return;
    if (x >= width || y >= height)
        return;
    put_pixel(base, pitch, bpp, x, y, rgb);
}
