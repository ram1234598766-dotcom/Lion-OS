/* LionOS kernel C support — Month 1 refinement.
 *
 * Freestanding C compiled by build.rs with -ffreestanding and linked into the
 * kernel ELF alongside the Rust core. This is the "C half" of the mixed-language
 * integration: the classic kernel-utility boilerplate a freestanding kernel
 * usually needs (bytewise memset/memcpy/memcmp) written in C rather than Rust.
 *
 * Constraints:
 *  - NO libc, NO headers, NO startup files. Types are declared here.
 *  - No 64-bit division / multiply into a libgcc helper — the kernel must not
 *    grow an unresolved libgcc dependency or a division-by-zero trap path.
 *  - position-dependent: compiled with -mcmodel=kernel -fno-pie to match the
 *    Rust kernel's static relocation model.
 */
typedef unsigned long size_t;

void *lion_memset(void *, int, size_t);
void *lion_memcpy(void *, const void *, size_t);
int   lion_memcmp(const void *, const void *, size_t);

void *lion_memset(void *dst, int c, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    while (n--) *d++ = (unsigned char)c;
    return dst;
}

void *lion_memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) *d++ = *s++;
    return dst;
}

int lion_memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *x = (const unsigned char *)a;
    const unsigned char *y = (const unsigned char *)b;
    while (n--) {
        int d = (int)*x++ - (int)*y++;
        if (d) return d;
    }
    return 0;
}

/* C calling assembly — the Rust -> C -> asm chain. `lion_cpuid` is the asm
 * routine in asm/cpu.s (SysV: leaf in edi, subleaf in esi, out[] in rdx). This
 * demonstrates the C half of the mixed-language stack and returns the CPUID
 * leaf-1 feature bits (edx), which the kernel prints at boot and CI greps. */
extern void lion_cpuid(unsigned int, unsigned int, unsigned int *);

unsigned int lion_cpu_leaf1_edx(void) {
    unsigned int out[4];
    lion_cpuid(1u, 0u, out);
    return out[3];
}