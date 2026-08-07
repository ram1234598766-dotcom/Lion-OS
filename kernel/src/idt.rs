//! Interrupt Descriptor Table — Month 2, kernel-core.
//!
//! A 256-gate IDT with 64-bit interrupt gates (type 0xE, ring 0). Handler
//! functions use the `extern "x86-interrupt"` ABI, which emits the exact
//! save/restore prologue and `iretq` epilogue. Fault vectors get structured
//! diagnostics (`LIONOS_FAULT vector=…`) instead of an unlabelled triple fault;
//! the two IRQ vectors we use (timer 0x20, keyboard 0x21) are wired after the
//! PIC remap in `interrupts.rs`.
//!
//! Layout matches Intel SDM 6.10.1; the pure packing is host-testable, the
//! handlers + `lidt` are gated to the freestanding target (`target_os="none"`).

// `asm` and `mem` are only used by the kernel-target paths (`init`, `idtr_of`).
#[cfg(target_os = "none")]
use core::arch::asm;
#[cfg(target_os = "none")]
use core::mem;

use crate::gdt::KERNEL_CODE;

/// CPU-pushed interrupt frame (RIP, CS, RFLAGS, RSP, SS) seen by an
/// `extern "x86-interrupt"` handler. Fields are the CPU's raw 64-bit values.
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct InterruptStackFrame {
    pub instruction_pointer: u64,
    pub code_segment: u64,
    pub cpu_flags: u64,
    pub stack_pointer: u64,
    pub stack_segment: u64,
}

/// One 16-byte IDT gate. `ist` byte = IST(3 bits) + reserved(5 bits).
/// `repr(C)`: the natural layout is exactly the SDM's (2+2+1+1+2+4+4 = 16, no
/// padding), and un-packed lets tests read fields without `E0793`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(C)]
pub struct IdtEntry {
    base_low: u16,
    selector: u16,
    ist: u8,
    type_attr: u8,
    base_mid: u16,
    base_hi: u32,
    reserved: u32,
}

impl IdtEntry {
    /// All-zero (not-present) gate — an "unhandled vector" trap if fired.
    pub const fn missing() -> Self {
        IdtEntry {
            base_low: 0,
            selector: 0,
            ist: 0,
            type_attr: 0,
            base_mid: 0,
            base_hi: 0,
            reserved: 0,
        }
    }

    /// A present 64-bit interrupt gate to `handler` on `selector`, with an
    /// optional IST index (0 = current stack). `handler` is a link address.
    pub const fn interrupt_gate(handler: u64, selector: u16, ist: u8) -> Self {
        let low = (handler & 0xFFFF) as u16;
        let mid = ((handler >> 16) & 0xFFFF) as u16;
        let hi = ((handler >> 32) & 0xFFFF_FFFF) as u32;
        IdtEntry {
            base_low: low,
            selector,
            // 0x8E = present | DPL0 | type 1110 (64-bit interrupt gate).
            ist: ist & 0x07,
            type_attr: 0x8E,
            base_mid: mid,
            base_hi: hi,
            reserved: 0,
        }
    }

    /// Reconstruct the 64-bit handler address (for tests).
    pub fn handler_address(&self) -> u64 {
        u64::from(self.base_low)
            | (u64::from(self.base_mid) << 16)
            | (u64::from(self.base_hi) << 32)
    }
}

/// The full 256-entry IDT.
pub const IDT_SIZE: usize = 256;

#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct Idt {
    entries: [IdtEntry; IDT_SIZE],
}

impl Idt {
    pub const fn new() -> Self {
        Idt { entries: [IdtEntry::missing(); IDT_SIZE] }
    }

    /// Install a gate. `index` is the raw vector (0..=255).
    pub fn set(&mut self, index: u8, handler: u64, ist: u8) {
        self.entries[index as usize] = IdtEntry::interrupt_gate(handler, KERNEL_CODE, ist);
    }

    pub fn get(&self, index: u8) -> IdtEntry {
        self.entries[index as usize]
    }
}

/// IDTR pseudo-descriptor for `lidt`.
/// `packed`: `lidt` reads limit at offset 0 (2 bytes) and base at offset 2
/// (8 bytes); `repr(C)` alone would pad base out to offset 8 and load garbage.
/// No `Debug` derive — `Debug` would borrow the packed u64 field (E0793).
#[derive(Clone, Copy)]
#[repr(C, packed)]
pub struct Idtr {
    limit: u16,
    base: u64,
}

#[cfg(target_os = "none")]
fn idtr_of(idt: &Idt) -> Idtr {
    let limit = (mem::size_of::<Idt>() - 1) as u16;
    Idtr { limit, base: idt as *const Idt as u64 }
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn divide_error(_: InterruptStackFrame) {
    fault_report(0x00, 0);
    fault_park();
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn invalid_opcode(_: InterruptStackFrame) {
    fault_report(0x06, 0);
    fault_park();
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn double_fault(frame: InterruptStackFrame, _error: u64) {
    fault_report(0x08, 0xDEAD);
    report_frame(frame);
    fault_park();
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn general_protection_fault(frame: InterruptStackFrame, error: u64) {
    fault_report(0x0D, error);
    report_frame(frame);
    fault_park();
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn page_fault(frame: InterruptStackFrame, error: u64) {
    fault_report(0x0E, error);
    report_frame(frame);
    ffi_read_cr2();
    fault_park();
}

#[cfg(target_os = "none")]
fn ffi_read_cr2() {
    // CR2 holds the faulting virtual address on #PF.
    let cr2: u64;
    unsafe {
        core::arch::asm!("mov {0}, cr2", out(reg) cr2, options(nomem, preserves_flags));
    }
    crate::serial::write_str("LIONOS_CR2=");
    crate::serial::write_hex(cr2);
    crate::serial::write_str("\r\n");
}

#[cfg(target_os = "none")]
fn fault_report(vector: u8, extra: u64) {
    crate::serial::write_str("\r\nLIONOS_FAULT vector=");
    crate::serial::write_hex(u64::from(vector));
    crate::serial::write_str(" info=");
    crate::serial::write_hex(extra);
    crate::serial::write_str("\r\n");
}

#[cfg(target_os = "none")]
fn report_frame(_frame: InterruptStackFrame) {
    crate::serial::write_str("LIONOS_FAULT_RIP=");
    crate::serial::write_hex(_frame.instruction_pointer);
    crate::serial::write_str("\r\n");
}

#[cfg(target_os = "none")]
fn fault_park() -> ! {
    loop {
        crate::ffi::hlt();
    }
}

/// Build and load the kernel IDT. Called once from `interrupts::init` (after
/// the PIC remap so the timer/keyboard vectors line up), before `sti`.
#[cfg(target_os = "none")]
pub fn init() {
    unsafe {
        let idt = &mut *core::ptr::addr_of_mut!(IDT);
        idt.set(0x00, divide_error as *const () as u64, 0);
        idt.set(0x06, invalid_opcode as *const () as u64, 0);
        idt.set(0x08, double_fault as *const () as u64, 1); // IST1 → the dedicated double-fault stack (gdt::setup)
        idt.set(0x0D, general_protection_fault as *const () as u64, 0);
        idt.set(0x0E, page_fault as *const () as u64, 0);

        let idtr = idtr_of(idt);
        asm!("lidt [{}]", in(reg) &idtr, options(nostack, preserves_flags));
    }
}

/// The kernel IDT. Boot-only mutation (interrupts are disabled until `sti`).
#[cfg(target_os = "none")]
static mut IDT: Idt = Idt::new();

/// Install an IRQ/vector gate after `lidt`. Mutates the static IDT in place;
/// because `lidt` loaded that table's *address*, the new gate is live as soon
/// as interrupts are enabled. Must be called before `sti`.
#[cfg(target_os = "none")]
pub fn install(index: u8, handler: u64, ist: u8) {
    unsafe {
        (&mut *core::ptr::addr_of_mut!(IDT)).set(index, handler, ist);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gate_is_16_bytes() {
        assert_eq!(core::mem::size_of::<IdtEntry>(), 16);
    }

    #[test]
    fn missing_gate_is_zero() {
        let e = IdtEntry::missing();
        assert_eq!(e.type_attr, 0);
        assert_eq!(e.handler_address(), 0);
    }

    #[test]
    fn gate_roundtrips_address_and_ist() {
        let addr: u64 = 0x0011_2233_4455_6677;
        let e = IdtEntry::interrupt_gate(addr, KERNEL_CODE, 3);
        assert_eq!(e.handler_address(), addr);
        assert_eq!(e.ist, 3);
        assert_eq!(e.type_attr, 0x8E);
        assert_eq!(e.selector, KERNEL_CODE);
    }

    #[test]
    fn ist_is_masked_to_3_bits() {
        let e = IdtEntry::interrupt_gate(0x1000, KERNEL_CODE, 0b1011);
        assert_eq!(e.ist, 0b011);
    }

    #[test]
    fn full_idt_holds_256_gates() {
        assert_eq!(IDT_SIZE, 256);
        let idt = Idt::new();
        assert_eq!(idt.get(255).type_attr, 0);
        assert_eq!(core::mem::size_of::<Idt>(), 256 * 16);
    }
}