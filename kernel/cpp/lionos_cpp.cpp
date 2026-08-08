// kernel/cpp/lionos_cpp.cpp — a first freestanding C++17 symbol the kernel links
// in. Freestanding: no exceptions, no RTTI, no threadsafe-statics, no libstdc++.
// The kernel heap allocator is Rust-owned (kernel/src/heap.rs), so this C++ code
// deliberately does NOT install a global `new`/`delete` here — a later driver
// (Task 4) that needs allocation does it where it owns a HeapAllocator.
extern "C" unsigned int lionos_cpp_magic(void) {
    return 0xC0FFEE0C; // deterministic marker for the boot-smoke CI grep
}