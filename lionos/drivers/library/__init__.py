"""Simulated driver library. Importing registers nothing; the kernel builds a
DriverBus with selected drivers (see build_driver_bus)."""
from ..core import CORE_DRIVERS
from .storage import (NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver,
                      TapeDriver, SanDriver)
from .compute import FPUDriver, RNGDriver, QuantumDriver
from .input_dev import (BrailleProxy, Touchscreen, StylusTablet, SpeechToText,
                        HotasJoystick, MidiKeyboard)
from .audio_media import (SoundBlasterMidi, PcmDecoder, VideoFrameDecoder,
                          CameraCapture, TtsSpeech, RomLoader)
from .graphics_display import (DisplaySwitcher, RefreshController,
                               AsciiRasterizer, UiScaling, EinkDisplay,
                               Haptics, Oscilloscope)
from .network import (WifiCard, FirewallRules, DhcpClient, VpnTunnel,
                      ProxyGateway, PacketSniffer, CdnCache, P2pDiscovery,
                      LoadBalancer, MeshRouter, GraphqlClient, EdgeCompute,
                      WebrtcStream, SshDaemon, ContainerRegistry)
from .security import (Fingerprint, SmartCard, SecureRNG, Sandbox, CaStore,
                       IdsScanner, KeyLogger, AclManager, VulnSimulator,
                       MemoryScrubber, AntiTamper, GdprScrubber, BlackBox)
from .diagnostics import (LoopbackTest, ThermalSensor, UpsDriver, LedBar,
                          BarcodeScanner, CrashDump, CoreDumpEvent, Watchdog,
                          PowerMeter, SatelliteLink, GpsProvider, GyroAccel,
                          AmbientLight, ServoActuator, TelemetryAggregator,
                          SmartLamp, CashDrawer, MagStripeReader, Plotter,
                          BiosLayer)
from .ipc_host import (HostClipboard, SharedMemoryIpc, SubprocessPipe,
                       DemuxSignal, Hypervisor, Vswitch, Kubelet, BusMaster)
from .enterprise import (JobQueue, FpgaLoader, SymbolicDebugger,
                         TimeMachineBackup, NvmeOverFabrics)
from .compliance import AuditLedger
from .dev_tools import JitProxy, MacroRecorder
from .ai_compute import NpuEmulator, VectorAccelerator

LIBRARY_DRIVERS = [
    # storage
    NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver, TapeDriver, SanDriver,
    # compute
    FPUDriver, RNGDriver, QuantumDriver,
    # input / accessibility
    BrailleProxy, Touchscreen, StylusTablet, SpeechToText, HotasJoystick, MidiKeyboard,
    # audio / media
    SoundBlasterMidi, PcmDecoder, VideoFrameDecoder, CameraCapture, TtsSpeech, RomLoader,
    # graphics / display
    DisplaySwitcher, RefreshController, AsciiRasterizer, UiScaling, EinkDisplay, Haptics, Oscilloscope,
    # network / cloud
    WifiCard, FirewallRules, DhcpClient, VpnTunnel, ProxyGateway, PacketSniffer, CdnCache,
    P2pDiscovery, LoadBalancer, MeshRouter, GraphqlClient, EdgeCompute, WebrtcStream,
    SshDaemon, ContainerRegistry,
    # security / crypto
    Fingerprint, SmartCard, SecureRNG, Sandbox, CaStore, IdsScanner, KeyLogger, AclManager,
    VulnSimulator, MemoryScrubber, AntiTamper, GdprScrubber, BlackBox,
    # diagnostics / power / environment
    LoopbackTest, ThermalSensor, UpsDriver, LedBar, BarcodeScanner, CrashDump, CoreDumpEvent,
    Watchdog, PowerMeter, SatelliteLink, GpsProvider, GyroAccel, AmbientLight, ServoActuator,
    TelemetryAggregator, SmartLamp, CashDrawer, MagStripeReader, Plotter, BiosLayer,
    # ipc / host
    HostClipboard, SharedMemoryIpc, SubprocessPipe, DemuxSignal, Hypervisor, Vswitch, Kubelet, BusMaster,
    # enterprise
    JobQueue, FpgaLoader, SymbolicDebugger, TimeMachineBackup, NvmeOverFabrics,
    # compliance
    AuditLedger,
    # dev tools
    JitProxy, MacroRecorder,
    # ai / compute
    NpuEmulator, VectorAccelerator,
]
