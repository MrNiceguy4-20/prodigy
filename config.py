"""
Configuration management for OpenCore Prodigy.

This module centralizes all configurable settings, constants, and defaults
to make the application more maintainable and customizable.
"""

from typing import Dict, List, Tuple

# Application Info
APP_NAME = "OpenCore Prodigy"
APP_VERSION = "0.5.0"

# ============================================================================== 
# Network Configuration
# ============================================================================== 

NETWORK_TIMEOUT = 30  # seconds
NETWORK_RETRIES = 3
NETWORK_BACKOFF_FACTOR = 1.5  # Exponential backoff multiplier
VERIFY_GPG_SIGNATURES = False  # Set to True when GPG support is needed
USE_MIRRORS = True  # Use mirror URLs as fallback

GITHUB_API = "https://api.github.com/repos"
USER_AGENT = "OpenCoreProdigy/0.5.0"

# ============================================================================== 
# Logging Configuration
# ============================================================================== 

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = "prodigy.log"
LOG_TO_FILE = True
LOG_TO_CONSOLE = True

# ============================================================================== 
# SMBIOS Models by Generation and Form Factor
# ============================================================================== 

SMBIOS_MODELS: Dict[str, Dict[int, str]] = {
    "laptop": {
        0: "MacBookPro11,1",  # Haswell and earlier
        1: "MacBookPro11,1",
        2: "MacBookPro11,1",
        3: "MacBookPro11,1",
        4: "MacBookPro11,1",
        5: "MacBookPro12,1",
        6: "MacBookPro14,1",
        7: "MacBookPro14,1",
        8: "MacBookPro15,2",
        9: "MacBookPro16,1",
        10: "MacBookPro16,1",
        11: "MacBookPro16,3",
        12: "MacBookPro16,3",
    },
    "desktop": {
        0: "iMac14,2",
        1: "iMac14,2",
        2: "iMac14,2",
        3: "iMac14,2",
        4: "iMac15,1",
        5: "iMac15,1",
        6: "iMac17,1",
        7: "iMac17,1",
        8: "iMac19,1",
        9: "iMac19,1",
        10: "iMac20,1",
        11: "MacPro7,1",
        12: "MacPro7,1",
    },
    "amd": {
        0: "iMacPro1,1",
    },
}

SMBIOS_FALLBACK = {
    "laptop": "MacBookPro15,2",
    "desktop": "iMac19,1",
    "unknown": "iMac19,1",
}

# ============================================================================== 
# macOS Versions and Compatibility
# ============================================================================== 

MACOS_VERSIONS = {
    "h": "High Sierra",
    "m": "Mojave",
    "c": "Catalina",
    "b": "Big Sur",
    "n": "Monterey",
    "v": "Ventura",
    "s": "Sonoma",
}

# ============================================================================== 
# Boot Arguments
# ============================================================================== 

BASE_BOOT_ARGS = ["-v"]  # Verbose mode

BOOT_ARGS_GPU: Dict[str, str] = {
    "uhd 630": "igfxfw=2",
    "uhd630": "igfxfw=2",
}

BOOT_ARGS_OCLP = [
    "-lilubetaall",
    "-wegtree",
    "-no_compat_check",
]

BOOT_ARGS_VENTURA_SONOMA = ["-allow_amfi"]

# ============================================================================== 
# GPU Markers for Compatibility Detection
# ============================================================================== 

GPU_MARKERS_NEED_OCLP = [
    "hd 3000",
    "hd 4000",
    "hd 4400",
    "hd 4600",
    "iris",
    "gtx",
    "gt ",
    "quadro",
    "kepler",
]

# ============================================================================== 
# Kext Specifications
# ============================================================================== 

KEXT_SPECS: Dict[str, Dict[str, str]] = {
    "Lilu.kext": {"repo": "acidanthera/Lilu", "asset": "RELEASE.zip"},
    "WhateverGreen.kext": {
        "repo": "acidanthera/WhateverGreen",
        "asset": "RELEASE.zip",
    },
    "VirtualSMC.kext": {
        "repo": "acidanthera/VirtualSMC",
        "asset": "RELEASE.zip",
    },
    "SMCProcessor.kext": {
        "repo": "acidanthera/VirtualSMC",
        "asset": "RELEASE.zip",
    },
    "SMCSuperIO.kext": {
        "repo": "acidanthera/VirtualSMC",
        "asset": "RELEASE.zip",
    },
    "AppleALC.kext": {"repo": "acidanthera/AppleALC", "asset": "RELEASE.zip"},
    "NVMeFix.kext": {"repo": "acidanthera/NVMeFix", "asset": "RELEASE.zip"},
    "RestrictEvents.kext": {
        "repo": "acidanthera/RestrictEvents",
        "asset": "RELEASE.zip",
    },
    "CPUFriend.kext": {
        "repo": "acidanthera/CPUFriend",
        "asset": "RELEASE.zip",
    },
    "AirportItlwm.kext": {
        "repo": "OpenIntelWireless/itlwm",
        "asset": "AirportItlwm",
    },
    "IntelBluetoothFirmware.kext": {
        "repo": "OpenIntelWireless/IntelBluetoothFirmware",
        "asset": "IntelBluetoothFirmware",
    },
    "RealtekRTL8111.kext": {
        "repo": "Mieze/RTL8111_driver_for_OS_X",
        "asset": "zip",
    },
    "LucyRTL8125Ethernet.kext": {
        "repo": "Mieze/LucyRTL8125Ethernet",
        "asset": "zip",
    },
    "AtherosE2200Ethernet.kext": {
        "repo": "Mieze/AtherosE2200Ethernet",
        "asset": "zip",
    },
    "USBToolBox.kext": {
        "repo": "USBToolBox/kext",
        "asset": "RELEASE.zip",
    },
    "UTBMap.kext": {"repo": "USBToolBox/kext", "asset": "RELEASE.zip"},
    "VoodooPS2Controller.kext": {
        "repo": "acidanthera/VoodooPS2",
        "asset": "RELEASE.zip",
    },
    "VoodooI2C.kext": {
        "repo": "VoodooI2C/VoodooI2C",
        "asset": "zip",
    },
    "VoodooHDA.kext": {
        "repo": "VoodooHDA/VoodooHDA",
        "asset": "pkg",
    },
}

# ============================================================================== 
# Driver Specifications
# ============================================================================== 

WANTED_DRIVERS = [
    "OpenRuntime.efi",
    "OpenCanopy.efi",
    "OpenHfsPlus.efi",
    "HfsPlus.efi",
]

# ============================================================================== 
# Tool Specifications
# ============================================================================== 

WANTED_TOOLS = [
    "acpidump.exe",
    "ocvalidate.exe",
    "macserial.exe",
    "gfxutil.exe",
]

# ============================================================================== 
# Directory Structure
# ============================================================================== 

DEFAULT_CACHE_DIR = "Cache"
DEFAULT_EFI_OUTPUT_DIR = "EFI_Output"

CACHE_SUBDIRS = [
    "Downloads",
    "ACPI",
    "OpenCore",
    "Kexts",
    "Drivers",
    "Tools",
]

# ============================================================================== 
# File Validation
# ============================================================================== 

CHECKSUM_ALGORITHM = "sha256"
MAX_FILE_SIZE_MB = 2048  # 2GB max for any single file

# ============================================================================== 
# Reserved Filenames (for security)
# ============================================================================== 

RESERVED_FILENAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "lpt1",
    "lpt2",
    "lpt3",
}

# ============================================================================== 
# Feature Flags
# ============================================================================== 

ENABLE_DRY_RUN = False
ENABLE_HARDWARE_EXPORT = True
ENABLE_BACKUP_EFI = True
ENABLE_PARALLEL_DOWNLOADS = False  # Set to True when implemented

# ============================================================================== 
# CPU Generation Detection
# ============================================================================== 

INTEL_GENERATIONS = {
    "i3-2": 2,
    "i5-2": 2,
    "i7-2": 2,
    "i3-3": 3,
    "i5-3": 3,
    "i7-3": 3,
}

# ============================================================================== 
# Secure Boot Models
# ============================================================================== 

SECURE_BOOT_MODELS = {
    "ventura": "Default",
    "sonoma": "Default",
    "monterey": "Disabled",
    "big sur": "Disabled",
    "catalina": "Disabled",
    "mojave": "Disabled",
    "high sierra": "Disabled",
}