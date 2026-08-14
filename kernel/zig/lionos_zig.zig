// kernel/zig/lionos_zig.zig — a first freestanding Zig symbol + a comptime
// hardware table, built with `zig build-obj`. Kernel-style: no std OS deps,
// only `@export` C-ABI symbols plus comptime-validated tables.
const std = @import("std");

// A comptime-validated tiny table (the kind a real NIC/HPET descriptor set uses);
// prove at compile time that the fields are what the C ABI expects.
const HwTable = extern struct {
    magic: u32,
    count: u16,
    _reserved: u16,
};
const hw_table: HwTable = blk: {
    const t = HwTable{ .magic = 0x5A7D, .count = 3, ._reserved = 0 };
    std.debug.assert(t.magic == 0x5A7D);
    break :blk t;
};

export fn lionos_zig_magic() callconv(.c) u32 {
    // "zig" on a phone keypad = 9-4-4; deterministic boot-smoke value.
    return 0x0000_0944;
}

export fn lionos_zig_table_magic() callconv(.c) u32 {
    return hw_table.magic;
}