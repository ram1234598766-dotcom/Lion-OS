/* string_utils.c — freestanding C string helpers (from lion-os-boilerplate,
 * integrated into LionOS per Month 1 of the master plan).
 *
 * Same build constraints as support.c: compiled by kernel/build.rs with
 * -ffreestanding -fno-builtin -nostdlib -nostdinc -mno-red-zone
 * -mcmodel=kernel -fno-pie. NO libc, NO standard headers — types are
 * declared here.
 *
 * These provide a C-side string bridge: a reference implementation to port
 * C string routines into the kernel without rewriting them in Rust first.
 * The kernel's own Rust code uses core::fmt for formatting; this module is
 * the deliberate cross-language integration point the plan's language lay
 * calls for (C for string/format helpers, NASM for port-I/O + CPU utils,
 * Rust for everything else).
 */

typedef unsigned long size_t;

/* lionos_strlen — number of bytes before the NUL terminator. */
size_t lionos_strlen(const char *s) {
    size_t n = 0;
    while (*s++) n++;
    return n;
}

/* lionos_strcmp — 0 if equal, <0 if a<b, >0 if a>b. */
int lionos_strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}

/* lionos_strcpy — copy src into dst incl. the NUL. NO bounds checking;
 * the caller guarantees dst is large enough. */
char *lionos_strcpy(char *dst, const char *src) {
    char *ret = dst;
    while ((*dst++ = *src++) != '\0') {}
    return ret;
}

/* lionos_itoa_hex — convert a 64-bit value to an ASCII hex string.
 * buf must be at least 19 bytes (0x + 16 hex chars + NUL). Used for printing
 * registers/addresses in early diagnostics before a full formatter is wired. */
void lionos_itoa_hex(unsigned long long val, char *buf) {
    const char *digits = "0123456789abcdef";
    buf[0] = '0'; buf[1] = 'x';
    for (int i = 0; i < 16; i++) {
        buf[2 + i] = digits[(val >> (60 - 4 * i)) & 0xF];
    }
    buf[18] = '\0';
}
