import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request

from ssdt_generator import SSDTGenerator  # full ACPI-aware SSDT generator


GITHUB_API = "https://api.github.com/repos"


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if os.name != "nt":
        return
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )
    sys.exit(0)


class EFIBuilder:
    """
    Automatic EFI builder with:
    - OpenCore download (latest stable)
    - Extended kext set (desktop + laptop)
    - Drivers + tools
    - ACPI dump via acpidump.exe
    - Full SSDT generation via SSDTGenerator
    - Full config.plist generation (OpenCore-style)
    - Persistent cache under ./Cache
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir = Path(base_dir or os.getcwd()).resolve()
        self.cache_dir = self.base_dir / "Cache"
        self.downloads_dir = self.cache_dir / "Downloads"
        self.acpi_dir = self.cache_dir / "ACPI"
        self.oc_cache_dir = self.cache_dir / "OpenCore"
        self.kext_cache_dir = self.cache_dir / "Kexts"
        self.driver_cache_dir = self.cache_dir / "Drivers"
        self.tools_cache_dir = self.cache_dir / "Tools"

        self._ensure_dirs()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #

    def _ensure_dirs(self) -> None:
        for d in (
            self.cache_dir,
            self.downloads_dir,
            self.acpi_dir,
            self.oc_cache_dir,
            self.kext_cache_dir,
            self.driver_cache_dir,
            self.tools_cache_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _http_get_json(self, url: str) -> Any:
        req = Request(url, headers={"User-Agent": "OpenCoreProdigy/1.0"})
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_download(self, url: str, dest: Path) -> Path:
        if dest.exists():
            return dest
        req = Request(url, headers={"User-Agent": "OpenCoreProdigy/1.0"})
        with urlopen(req) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return dest

    # ------------------------------------------------------------------ #
    # GitHub release helpers
    # ------------------------------------------------------------------ #

    def _get_latest_release_asset(
        self,
        repo: str,
        asset_match: str,
    ) -> Optional[Dict[str, Any]]:
        api_url = f"{GITHUB_API}/{repo}/releases/latest"
        data = self._http_get_json(api_url)
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if asset_match in name:
                return asset
        return None

    def _download_release_asset(
        self,
        repo: str,
        asset_match: str,
        cache_dir: Path,
    ) -> Path:
        asset = self._get_latest_release_asset(repo, asset_match)
        if not asset:
            raise RuntimeError(f"Asset '{asset_match}' not found in {repo} latest release")

        url = asset["browser_download_url"]
        name = asset["name"]
        dest = cache_dir / name
        return self._http_download(url, dest)

    # ------------------------------------------------------------------ #
    # OpenCore
    # ------------------------------------------------------------------ #

    def prepare_opencore(self) -> Path:
        print("  - Downloading latest OpenCore release...")
        zip_path = self._download_release_asset(
            "acidanthera/OpenCorePkg",
            "RELEASE.zip",
            self.oc_cache_dir,
        )

        extract_dir = self.oc_cache_dir / zip_path.stem
        if not extract_dir.exists():
            print("  - Extracting OpenCore...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

        oc_root = None
        for p in extract_dir.rglob("OpenCore.efi"):
            oc_root = p.parent.parent
            break

        if not oc_root:
            raise RuntimeError("Could not locate OpenCore.efi in extracted archive")

        print(f"  - OpenCore ready at: {oc_root}")
        return oc_root

    # ------------------------------------------------------------------ #
    # Kexts
    # ------------------------------------------------------------------ #

    def _kext_specs(self) -> Dict[str, Dict[str, str]]:
        return {
            "Lilu.kext": {"repo": "acidanthera/Lilu", "asset": "RELEASE.zip"},
            "WhateverGreen.kext": {"repo": "acidanthera/WhateverGreen", "asset": "RELEASE.zip"},
            "VirtualSMC.kext": {"repo": "acidanthera/VirtualSMC", "asset": "RELEASE.zip"},
            "SMCProcessor.kext": {"repo": "acidanthera/VirtualSMC", "asset": "RELEASE.zip"},
            "SMCSuperIO.kext": {"repo": "acidanthera/VirtualSMC", "asset": "RELEASE.zip"},
            "AppleALC.kext": {"repo": "acidanthera/AppleALC", "asset": "RELEASE.zip"},
            "NVMeFix.kext": {"repo": "acidanthera/NVMeFix", "asset": "RELEASE.zip"},
            "RestrictEvents.kext": {"repo": "acidanthera/RestrictEvents", "asset": "RELEASE.zip"},
            "CPUFriend.kext": {"repo": "acidanthera/CPUFriend", "asset": "RELEASE.zip"},
            "AirportItlwm.kext": {"repo": "OpenIntelWireless/itlwm", "asset": "AirportItlwm"},
            "IntelBluetoothFirmware.kext": {"repo": "OpenIntelWireless/IntelBluetoothFirmware", "asset": "IntelBluetoothFirmware"},
            "RealtekRTL8111.kext": {"repo": "Mieze/RTL8111_driver_for_OS_X", "asset": "zip"},
            "LucyRTL8125Ethernet.kext": {"repo": "Mieze/LucyRTL8125Ethernet", "asset": "zip"},
            "AtherosE2200Ethernet.kext": {"repo": "Mieze/AtherosE2200Ethernet", "asset": "zip"},
            "USBToolBox.kext": {"repo": "USBToolBox/kext", "asset": "RELEASE.zip"},
            "UTBMap.kext": {"repo": "USBToolBox/kext", "asset": "RELEASE.zip"},
            "VoodooPS2Controller.kext": {"repo": "acidanthera/VoodooPS2", "asset": "RELEASE.zip"},
            "VoodooI2C.kext": {"repo": "VoodooI2C/VoodooI2C", "asset": "zip"},
            "VoodooHDA.kext": {"repo": "VoodooHDA/VoodooHDA", "asset": "pkg"},
        }

    def prepare_kexts(self) -> Dict[str, Path]:
        print("  - Preparing kexts (extended universal set)...")
        kext_paths: Dict[str, Path] = {}
        specs = self._kext_specs()

        for kext_name, spec in specs.items():
            repo = spec["repo"]
            asset_match = spec["asset"]

            try:
                zip_path = self._download_release_asset(
                    repo,
                    asset_match,
                    self.kext_cache_dir,
                )
            except Exception as e:
                print(f"    ! Failed to download {kext_name} from {repo}: {e}")
                continue

            extract_dir = self.kext_cache_dir / f"{zip_path.stem}_{kext_name}"
            if not extract_dir.exists():
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(extract_dir)
                except zipfile.BadZipFile:
                    continue

            found = None
            for p in extract_dir.rglob(kext_name):
                if p.is_dir() and p.suffix == ".kext":
                    found = p
                    break

            if found:
                kext_paths[kext_name] = found
                print(f"    - {kext_name} ready")
            else:
                print(f"    ! {kext_name} not found in extracted archive")

        return kext_paths

    # ------------------------------------------------------------------ #
    # Drivers
    # ------------------------------------------------------------------ #

    def prepare_drivers(self, oc_root: Path) -> Dict[str, Path]:
        print("  - Preparing drivers...")
        drivers_dir = oc_root / "Drivers"
        driver_paths: Dict[str, Path] = {}

        wanted = [
            "OpenRuntime.efi",
            "OpenCanopy.efi",
            "OpenHfsPlus.efi",
            "HfsPlus.efi",
        ]

        for w in wanted:
            for p in drivers_dir.rglob(w):
                driver_paths[w] = p
                print(f"    - {w} ready")
                break

        return driver_paths

    # ------------------------------------------------------------------ #
    # Tools (including acpidump, macserial, etc.)
    # ------------------------------------------------------------------ #

    def prepare_tools(self) -> Dict[str, Path]:
    print("  - Preparing tools (acpidump, macserial, gfxutil, ocvalidate)...")
    tools: Dict[str, Path] = {}

    # Tools are now inside the main OpenCore RELEASE.zip under Utilities/
    zip_path = self._download_release_asset(
        "acidanthera/OpenCorePkg",
        "RELEASE.zip",
        self.tools_cache_dir,
    )

    extract_dir = self.tools_cache_dir / zip_path.stem
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

    # Tools we want to extract
    wanted = [
        "acpidump.exe",
        "ocvalidate.exe",
        "macserial.exe",
        "gfxutil.exe",
    ]

    for name in wanted:
        found = None
        for p in extract_dir.rglob(name):
            if p.is_file():
                found = p
                break

        if found:
            tools[name] = found
            print(f"    - {name} ready")
        else:
            print(f"    ! {name} not found in OpenCore Utilities")

    return tools


    # ------------------------------------------------------------------ #
    # ACPI dump + SSDT generation
    # ------------------------------------------------------------------ #

    def dump_acpi(self, acpidump_path: Path) -> Path:
        if not is_admin():
            print("\nAdministrator privileges are required to dump ACPI tables.")
            print("Relaunching with elevation...\n")
            time.sleep(1)
            relaunch_as_admin()

        self.acpi_dir.mkdir(parents=True, exist_ok=True)

        print("  - Dumping ACPI tables with acpidump.exe...")
        # Dump all tables (-b -z) so SSDTGenerator can see everything
        cmd = [str(acpidump_path), "-b", "-z"]
        try:
            subprocess.run(
                cmd,
                cwd=self.acpi_dir,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            print("    ! acpidump.exe failed, continuing with whatever ACPI data is available")

        # acpidump -b -z produces multiple .dat and acpi.bin; we just return the directory
        print(f"  - ACPI dump directory: {self.acpi_dir}")
        return self.acpi_dir

    def generate_ssdts(self, acpi_dump_dir: Path, acpi_out_dir: Path) -> None:
        print("  - Generating SSDTs via SSDTGenerator...")
        acpi_out_dir.mkdir(parents=True, exist_ok=True)
        try:
            gen = SSDTGenerator(acpi_dump_dir)
            gen.generate_all(acpi_out_dir)
            print("    - SSDT generation complete")
        except Exception as e:
            print(f"    ! SSDT generation failed: {e}")

    # ------------------------------------------------------------------ #
    # macOS target selection + OCLP logic
    # ------------------------------------------------------------------ #

    def _prompt_macos_target(self, compatibility_report: Dict[str, Any]) -> str:
        recommended = compatibility_report.get("RecommendedVersion", "Unknown")
        print("\n=== macOS Target Selection ===")
        print(f"Recommended macOS (if available): {recommended}\n")
        print("Build EFI for which macOS?")
        print("  [H] High Sierra")
        print("  [M] Mojave")
        print("  [C] Catalina")
        print("  [B] Big Sur")
        print("  [N] Monterey")
        print("  [V] Ventura")
        print("  [S] Sonoma")

        mapping = {
            "h": "High Sierra",
            "m": "Mojave",
            "c": "Catalina",
            "b": "Big Sur",
            "n": "Monterey",
            "v": "Ventura",
            "s": "Sonoma",
        }

        while True:
            choice = input("\nEnter choice: ").strip().lower()
            if choice in mapping:
                target = mapping[choice]
                print(f"\n  - macOS target set to: {target}\n")
                return target
            print("  ! Invalid choice, please try again.")

    def _needs_ocl_patches(self, hardware_report: Dict[str, Any], macos_target: str) -> bool:
        # Very simple heuristic: Ventura/Sonoma + older Intel iGPU or NVIDIA
        if macos_target not in ("Ventura", "Sonoma"):
            return False

        gpus = hardware_report.get("GPU", {})
        gpu_names = " ".join(gpus.keys()).lower()

        # Rough detection of problematic GPUs
        bad_markers = [
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
        if any(m in gpu_names for m in bad_markers):
            return True

        # Very old CPUs with no clear GPU info
        cpu_name = hardware_report.get("CPU", {}).get("Processor Name", "").lower()
        if any(gen in cpu_name for gen in ("i3-2", "i5-2", "i7-2", "i3-3", "i5-3", "i7-3")):
            return True

        return False

    def _prompt_enable_ocl_patches(self) -> bool:
        while True:
            ans = input("Enable OCLP-style patches automatically? (y/n): ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            print("  ! Please answer y or n.")

    # ------------------------------------------------------------------ #
    # SMBIOS selection + serial generation
    # ------------------------------------------------------------------ #

    def _detect_cpu_generation(self, cpu_name: str) -> Optional[int]:
        # Very rough Intel gen detection from model number (e.g., i7-8700K -> 8th gen)
        import re

        m = re.search(r"i[3579]-([0-9]{4,5})", cpu_name)
        if not m:
            return None
        num = m.group(1)
        try:
            first = int(num[0])
        except ValueError:
            return None
        # 2xxx -> 2nd, 3xxx -> 3rd, ..., 9xxx -> 9th, 10xxx -> 10th, etc.
        if len(num) == 4:
            return first
        if len(num) == 5:
            return int(num[:2])
        return None

    def _select_smbios_model(self, hardware_report: Dict[str, Any], macos_target: str) -> str:
        form_factor = hardware_report.get("FormFactor", "Desktop")
        cpu_name = hardware_report.get("CPU", {}).get("Processor Name", "")
        gpus = hardware_report.get("GPU", {})
        gpu_names = " ".join(gpus.keys()).lower()

        cpu_gen = self._detect_cpu_generation(cpu_name.lower()) or 8

        # AMD / unknown CPU: prefer MacPro1,1 / iMacPro1,1 style
        if "ryzen" in cpu_name.lower() or "epyc" in cpu_name.lower():
            if "laptop" in form_factor.lower():
                return "MacBookPro16,3"
            return "iMacPro1,1"

        # Desktop vs laptop split
        if "laptop" in form_factor.lower():
            # Laptops
            if cpu_gen <= 4:
                return "MacBookPro11,1"
            if cpu_gen == 5:
                return "MacBookPro12,1"
            if cpu_gen == 6 or cpu_gen == 7:
                return "MacBookPro14,1"
            if cpu_gen == 8:
                return "MacBookPro15,2"
            if cpu_gen == 9 or cpu_gen == 10:
                return "MacBookPro16,1"
            if cpu_gen >= 11:
                return "MacBookPro16,3"
        else:
            # Desktops
            if cpu_gen <= 4:
                return "iMac14,2"
            if cpu_gen == 5:
                return "iMac15,1"
            if cpu_gen == 6 or cpu_gen == 7:
                return "iMac17,1"
            if cpu_gen == 8:
                return "iMac19,1"
            if cpu_gen == 9:
                return "iMac19,1"
            if cpu_gen == 10:
                return "iMac20,1"
            if cpu_gen >= 11:
                # 11th+ gen: MacPro7,1 is safest
                return "MacPro7,1"

        # Fallback
        return "iMac19,1"

    def _run_macserial(self, macserial_path: Path, smbios: str) -> Dict[str, str]:
        # macserial -m iMac19,1 -n 1
        try:
            cmd = [str(macserial_path), "-m", smbios, "-n", "1"]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        except Exception:
            return {}

        # Output format: Model | Serial | Board Serial | SmUUID
        # Example: iMac19,1 | C02XXX | C027XXX | XXXXX-XXXX-...
        parts = out.strip().split("|")
        if len(parts) < 4:
            return {}

        serial = parts[1].strip()
        mlb = parts[2].strip()
        smuuid = parts[3].strip()

        return {
            "SystemSerialNumber": serial,
            "MLB": mlb,
            "SystemUUID": smuuid,
        }

    # ------------------------------------------------------------------ #
    # Boot-args + quirks
    # ------------------------------------------------------------------ #

    def _build_boot_args(
        self,
        macos_target: str,
        oclp_enabled: bool,
        hardware_report: Dict[str, Any],
    ) -> str:
        args: List[str] = []

        # Base args
        args.extend(["-v"])

        # GPU / iGPU related
        gpus = hardware_report.get("GPU", {})
        gpu_names = " ".join(gpus.keys()).lower()
        if "uhd 630" in gpu_names or "uhd630" in gpu_names:
            # Common for Coffee Lake
            args.append("igfxfw=2")

        # OCLP-style patches if enabled
        if oclp_enabled:
            args.extend(
                [
                    "-lilubetaall",
                    "-wegtree",
                    "-no_compat_check",
                ]
            )

        # macOS-specific tweaks (minimal)
        if macos_target in ("Ventura", "Sonoma"):
            args.append("-allow_amfi")

        return " ".join(args)

    def _secure_boot_model_for(self, smbios: str, macos_target: str) -> str:
        # Simple mapping: newer SMBIOS -> Default, older -> Disabled
        if macos_target in ("Ventura", "Sonoma"):
            return "Default"
        return "Disabled"

    # ------------------------------------------------------------------ #
    # Config.plist generation
    # ------------------------------------------------------------------ #

    def write_config_plist(
        self,
        efi_oc_dir: Path,
        acpi_out_dir: Path,
        kexts_out_dir: Path,
        drivers_out_dir: Path,
        tools: Dict[str, Path],
        hardware_report: Dict[str, Any],
        compatibility_report: Dict[str, Any],
        macos_target: str,
        oclp_enabled: bool,
    ) -> None:
        import plistlib

        config_path = efi_oc_dir / "config.plist"
        print(f"  - Writing config.plist at: {config_path}")

        # ACPI/Add: all .aml in ACPI dir
        acpi_add: List[Dict[str, Any]] = []
        for aml in sorted(acpi_out_dir.glob("*.aml")):
            acpi_add.append(
                {
                    "Path": aml.name,
                    "Enabled": True,
                    "Comment": "",
                    "OemTableId": "",
                    "TableLength": 0,
                    "TableSignature": "",
                }
            )

        # Kernel/Add: all kexts in Kexts dir
        kernel_add: List[Dict[str, Any]] = []
        for kext in sorted(kexts_out_dir.glob("*.kext")):
            kernel_add.append(
                {
                    "BundlePath": kext.name,
                    "Enabled": True,
                    "ExecutablePath": "Contents/MacOS/" + kext.stem,
                    "PlistPath": "Contents/Info.plist",
                    "Comment": "",
                    "MaxKernel": "",
                    "MinKernel": "",
                }
            )

        # UEFI/Drivers: all .efi in Drivers dir
        uefi_drivers: List[str] = []
        for drv in sorted(drivers_out_dir.glob("*.efi")):
            uefi_drivers.append(drv.name)

        # SMBIOS + serials
        smbios_model = self._select_smbios_model(hardware_report, macos_target)
        serials: Dict[str, str] = {}
        macserial_path = tools.get("macserial.exe")
        if macserial_path:
            serials = self._run_macserial(macserial_path, smbios_model)
        if not serials:
            # Fallback: dummy values (user should replace)
            serials = {
                "SystemSerialNumber": "C02XXXXXXX",
                "MLB": "C027XXXXXXXXXXX",
                "SystemUUID": str(uuid.uuid4()).upper(),
            }

        # ROM: simple placeholder (user can replace with real MAC)
        rom_bytes = b"\x11\x22\x33\x44\x55\x66"

        boot_args = self._build_boot_args(macos_target, oclp_enabled, hardware_report)
        secure_boot_model = self._secure_boot_model_for(smbios_model, macos_target)

        config: Dict[str, Any] = {
            "ACPI": {
                "Add": acpi_add,
                "Delete": [],
                "Patch": [],
                "Quirks": {
                    "FadtEnableReset": True,
                    "NormalizeHeaders": True,
                    "RebaseRegions": False,
                    "ResetHwSig": False,
                    "ResetLogoStatus": True,
                },
            },
            "Booter": {
                "MmioWhitelist": [],
                "Patch": [],
                "Quirks": {
                    "AvoidRuntimeDefrag": True,
                    "DevirtualiseMmio": True,
                    "DisableSingleUser": False,
                    "DisableVariableWrite": False,
                    "DiscardHibernateMap": True,
                    "EnableSafeModeSlide": True,
                    "EnableWriteUnprotector": True,
                    "ForceBooterSignature": False,
                    "ForceExitBootServices": False,
                    "ProtectMemoryRegions": False,
                    "ProtectSecureBoot": False,
                    "ProtectUefiServices": True,
                    "ProvideCustomSlide": True,
                    "ProvideMaxSlide": 0,
                    "RebuildAppleMemoryMap": True,
                    "SetupVirtualMap": True,
                    "SignalAppleOS": True,
                    "SyncRuntimePermissions": True,
                },
            },
            "DeviceProperties": {
                "Add": {},
                "Delete": {},
            },
            "Kernel": {
                "Add": kernel_add,
                "Block": [],
                "Emulate": {
                    "Cpuid1Data": b"",
                    "Cpuid1Mask": b"",
                    "DummyPowerManagement": False,
                    "MaxKernel": "",
                    "MinKernel": "",
                },
                "Force": [],
                "Patch": [],
                "Quirks": {
                    "AppleCpuPmCfgLock": False,
                    "AppleXcpmCfgLock": False,
                    "AppleXcpmExtraMsrs": False,
                    "AppleXcpmForceBoost": False,
                    "CustomSMBIOSGuid": True,
                    "DisableIoMapper": True,
                    "DisableLinkeditJettison": True,
                    "DisableRtcChecksum": False,
                    "ExtendBTFeatureFlags": True,
                    "ExternalDiskIcons": False,
                    "ForceSecureBootScheme": False,
                    "IncreasePciBarSize": False,
                    "LapicKernelPanic": False,
                    "LegacyCommpage": False,
                    "PanicNoKextDump": True,
                    "PowerTimeoutKernelPanic": True,
                    "ProvideCurrentCpuInfo": True,
                    "SetApfsTrimTimeout": -1,
                    "ThirdPartyDrives": False,
                    "XhciPortLimit": False,
                },
                "Scheme": {
                    "FuzzyMatch": True,
                    "KernelArch": "x86_64",
                    "KernelCache": "Auto",
                },
            },
            "Misc": {
                "Boot": {
                    "ConsoleAttributes": 0,
                    "HibernateMode": "None",
                    "PickerAttributes": 1,
                    "PickerMode": "External",
                    "PickerVariant": "Auto",
                    "PollAppleHotKeys": True,
                    "ShowPicker": True,
                    "Timeout": 5,
                },
                "Debug": {
                    "AppleDebug": False,
                    "ApplePanic": False,
                    "DisableWatchDog": True,
                    "DisplayDelay": 0,
                    "DisplayLevel": 2147483650,
                    "SerialInit": False,
                    "SysReport": False,
                },
                "Security": {
                    "AllowNvramReset": True,
                    "AllowSetDefault": True,
                    "AuthRestart": False,
                    "BlacklistAppleUpdate": False,
                    "BootProtect": "Bootstrap",
                    "ExposeSensitiveData": 6,
                    "HaltLevel": 2147483648,
                    "ScanPolicy": 0,
                    "SecureBootModel": secure_boot_model,
                    "Vault": "Optional",
                },
                "Tools": [],
            },
            "NVRAM": {
                "Add": {
                    "7C436110-AB2A-4BBB-A880-FE41995C9F82": {
                        "boot-args": boot_args,
                        "csr-active-config": b"\x00\x00\x00\x00",
                        "run-efi-updater": "No",
                        "prev-lang:kbd": b"en-US:0",
                    },
                    "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": {
                        "UIScale": 1,
                        "DefaultBackgroundColor": b"\x00\x00\x00\x00",
                    },
                },
                "Delete": {},
                "LegacyEnable": False,
                "LegacyOverwrite": False,
                "LegacySchema": {},
                "WriteFlash": True,
            },
            "PlatformInfo": {
                "Automatic": True,
                "Generic": {
                    "MLB": serials["MLB"],
                    "ROM": rom_bytes,
                    "SystemProductName": smbios_model,
                    "SystemSerialNumber": serials["SystemSerialNumber"],
                    "SystemUUID": serials["SystemUUID"],
                },
                "UpdateDataHub": True,
                "UpdateNVRAM": True,
                "UpdateSMBIOS": True,
                "UpdateSMBIOSMode": "Create",
            },
            "UEFI": {
                "APFS": {
                    "EnableJumpstart": True,
                    "GlobalConnect": False,
                    "HideVerbose": True,
                    "JumpstartHotPlug": False,
                    "MinDate": 0,
                    "MinVersion": 0,
                },
                "Audio": {
                    "AudioCodec": 0,
                    "AudioDevice": "PciRoot(0x0)/Pci(0x1b,0x0)",
                    "AudioOut": 0,
                    "AudioSupport": False,
                    "MinimumVolume": 20,
                    "PlayChime": "Auto",
                    "VolumeAmplifier": 0,
                },
                "ConnectDrivers": True,
                "Drivers": uefi_drivers,
                "Input": {
                    "KeyFiltering": False,
                    "KeyForgetThreshold": 5,
                    "KeyMergeThreshold": 2,
                    "KeySupport": True,
                    "KeySupportMode": "Auto",
                    "KeySwap": False,
                    "PointerSupport": False,
                    "PointerSupportMode": "ASUS",
                    "TimerResolution": 50000,
                },
                "Output": {
                    "ClearScreenOnModeSwitch": False,
                    "ConsoleMode": "",
                    "DirectGopRendering": False,
                    "IgnoreTextInGraphics": False,
                    "ProvideConsoleGop": True,
                    "ReconnectGraphicsOnConnect": False,
                    "ReconnectOnResChange": False,
                    "ReplaceTabWithSpace": False,
                    "Resolution": "Max",
                    "SanitiseClearScreen": False,
                    "TextRenderer": "BuiltinGraphics",
                },
                "ProtocolOverrides": {
                    "AppleAudio": False,
                    "AppleBootPolicy": False,
                    "AppleDebugLog": False,
                    "AppleEvent": False,
                    "AppleFramebufferInfo": False,
                    "AppleImageConversion": False,
                    "AppleKeyMap": False,
                    "AppleRtcRam": False,
                    "AppleSmcIo": False,
                    "AppleUserInterfaceTheme": False,
                    "DataHub": False,
                    "DeviceProperties": False,
                    "FirmwareVolume": False,
                    "HashServices": False,
                    "OSInfo": False,
                    "UnicodeCollation": False,
                },
                "Quirks": {
                    "DeduplicateBootOrder": True,
                    "ExitBootServicesDelay": 0,
                    "IgnoreInvalidFlexRatio": True,
                    "ReleaseUsbOwnership": False,
                    "RequestBootVarRouting": True,
                    "TscSyncTimeout": 0,
                    "UnblockFsConnect": False,
                },
                "ReservedMemory": [],
            },
        }

        with open(config_path, "wb") as f:
            plistlib.dump(config, f)

    # ------------------------------------------------------------------ #
    # EFI assembly
    # ------------------------------------------------------------------ #

    def build_efi(
        self,
        hardware_report: Dict[str, Any],
        compatibility_report: Dict[str, Any],
        output_dir: str,
    ) -> Path:
        out_root = Path(output_dir).resolve()
        efi_dir = out_root / "EFI"
        oc_dir = efi_dir / "OC"
        acpi_out_dir = oc_dir / "ACPI"
        kexts_out_dir = oc_dir / "Kexts"
        drivers_out_dir = oc_dir / "Drivers"
        tools_out_dir = oc_dir / "Tools"
        resources_out_dir = oc_dir / "Resources"

        print("\n=== EFI Builder ===\n")
        print(f"Target output directory:\n  {out_root}\n")

        if efi_dir.exists():
            print("An EFI folder already exists in this location.")
            ans = input("Replace it? (y/n): ").strip().lower()
            if ans != "y":
                print("\nEFI build cancelled.\n")
                return efi_dir
            print("  - Removing existing EFI folder...")
            shutil.rmtree(efi_dir)

        print("  - Creating EFI folder structure...")
        for d in (
            efi_dir,
            oc_dir,
            acpi_out_dir,
            kexts_out_dir,
            drivers_out_dir,
            tools_out_dir,
            resources_out_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        # Show basic hardware summary
        cpu_name = hardware_report.get("CPU", {}).get("Processor Name", "Unknown CPU")
        gpus = hardware_report.get("GPU", {})
        gpu_list = ", ".join(gpus.keys()) if gpus else "Unknown GPU"
        form_factor = hardware_report.get("FormFactor", "Unknown")

        print("Detected hardware:")
        print(f"  CPU: {cpu_name}")
        print(f"  GPU: {gpu_list}")
        print(f"  Form Factor: {form_factor}\n")

        # macOS target selection
        macos_target = self._prompt_macos_target(compatibility_report)

        # Prepare OpenCore
        oc_root = self.prepare_opencore()

        # Drivers
        drivers = self.prepare_drivers(oc_root)
        for name, path in drivers.items():
            shutil.copy2(path, drivers_out_dir / name)

        # Tools
        tools = self.prepare_tools()
        for name, path in tools.items():
            shutil.copy2(path, tools_out_dir / name)

        # ACPI dump + SSDTs
        acpidump_path = tools.get("acpidump.exe")
        if acpidump_path:
            acpi_dump_dir = self.dump_acpi(acpidump_path)
            self.generate_ssdts(acpi_dump_dir, acpi_out_dir)
        else:
            print("  ! acpidump.exe not available; skipping ACPI dump and SSDT generation")

        # Kexts
        kexts = self.prepare_kexts()
        for name, path in kexts.items():
            dest = kexts_out_dir / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(path, dest)

        # OCLP requirement + prompt
        needs_ocl = self._needs_ocl_patches(hardware_report, macos_target)
        oclp_enabled = False
        if needs_ocl:
            print("WARNING: Your hardware likely requires OCLP-style patches for this macOS target.")
            oclp_enabled = self._prompt_enable_ocl_patches()

        # Config.plist
        self.write_config_plist(
            oc_dir,
            acpi_out_dir,
            kexts_out_dir,
            drivers_out_dir,
            tools,
            hardware_report,
            compatibility_report,
            macos_target,
            oclp_enabled,
        )

        print("\nEFI build complete.")
        print(f"EFI folder created at:\n  {efi_dir}\n")

        return efi_dir
