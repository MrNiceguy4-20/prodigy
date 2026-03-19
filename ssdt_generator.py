import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SSDTGenerator:
    """
    Full ACPI-aware SSDT generator (SSDTs only, no DSDT modification).

    Responsibilities:
      - Ensure iasl is available
      - Decompile ACPI tables (DSDT + SSDTs) to DSL
      - Parse DSDT.dsl into a structured representation
      - Generate dynamic SSDTs (EC, PLUG, USBX, PNLF, AWAC, HPET, SBUS, XOSI, IMEI, RTC0, etc.)
      - Compile DSL → AML and write into EFI/OC/ACPI
    """

    def __init__(self, acpi_dump_dir: Path) -> None:
        self.acpi_dump_dir = Path(acpi_dump_dir).resolve()
        self.iasl_path = self._ensure_iasl()

        self.dsl_cache: Dict[str, str] = {}
        self.devices: Dict[str, List[Tuple[str, str]]] = {}
        self.cpu_scope: Optional[str] = None
        self.has_awac: bool = False
        self.has_rtc: bool = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_all(self, out_dir: Path) -> None:
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        self._decompile_all()
        self._parse_dsdt()

        # Generate all SSDTs (as requested)
        self._gen_ssdt_ec(out_dir)
        self._gen_ssdt_plug(out_dir)
        self._gen_ssdt_usbx(out_dir)
        self._gen_ssdt_pnlf(out_dir)
        self._gen_ssdt_awac(out_dir)
        self._gen_ssdt_hpet(out_dir)
        self._gen_ssdt_sbus(out_dir)
        self._gen_ssdt_xosi(out_dir)
        self._gen_ssdt_imei(out_dir)
        self._gen_ssdt_rtc0(out_dir)
        self._gen_ssdt_als0(out_dir)
        self._gen_ssdt_gprw(out_dir)
        self._gen_ssdt_usb_reset(out_dir)

    # ------------------------------------------------------------------ #
    # iasl handling
    # ------------------------------------------------------------------ #

    def _ensure_iasl(self) -> str:
        # Try PATH first
        if self._cmd_exists("iasl"):
            return "iasl"

        # Fallback: local tools directory
        tools_dir = self.acpi_dump_dir / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        iasl_exe = tools_dir / ("iasl.exe" if os.name == "nt" else "iasl")

        if iasl_exe.exists():
            return str(iasl_exe)

        # Minimal embedded iasl download stub (user can replace with real URL if desired)
        # For now, we just require iasl to be present or installed manually.
        raise RuntimeError(
            "iasl not found. Please install iasl and ensure it is in PATH, "
            "or place it in ACPI dump 'tools' directory."
        )

    def _cmd_exists(self, cmd: str) -> bool:
        from shutil import which

        return which(cmd) is not None

    # ------------------------------------------------------------------ #
    # Decompilation
    # ------------------------------------------------------------------ #

    def _decompile_all(self) -> None:
        aml_files = list(self.acpi_dump_dir.glob("*.aml"))
        if not aml_files:
            raise RuntimeError("No .aml files found in ACPI dump directory")

        cmd = [self.iasl_path, "-da", "-dl"] + [str(f.name) for f in aml_files]
        subprocess.run(cmd, cwd=self.acpi_dump_dir, check=True)

    # ------------------------------------------------------------------ #
    # DSDT parsing (AST-like structure)
    # ------------------------------------------------------------------ #

    def _parse_dsdt(self) -> None:
        dsdt_dsl = self.acpi_dump_dir / "DSDT.dsl"
        if not dsdt_dsl.exists():
            raise RuntimeError("DSDT.dsl not found after decompilation")

        text = dsdt_dsl.read_text(encoding="utf-8", errors="ignore")
        self.dsl_cache["DSDT"] = text

        self._parse_devices(text)
        self._detect_cpu_scope(text)
        self._detect_timers(text)

    def _parse_devices(self, text: str) -> None:
        """
        Very lightweight structural parser:
          - Finds Device (XXXX) blocks
          - Tracks their full ACPI path based on Scope nesting
        """
        scope_stack: List[str] = ["\\"]  # root
        lines = text.splitlines()

        current_path = "\\"
        for line in lines:
            line_stripped = line.strip()

            # Scope
            m_scope = re.match(r"Scope\s+\(([^)]+)\)", line_stripped)
            if m_scope:
                scope = m_scope.group(1).strip()
                scope_stack.append(scope)
                current_path = ".".join(scope_stack)
                continue

            if line_stripped.startswith("}"):
                if len(scope_stack) > 1:
                    scope_stack.pop()
                    current_path = ".".join(scope_stack)
                continue

            # Device
            m_dev = re.match(r"Device\s+\(([^)]+)\)", line_stripped)
            if m_dev:
                dev_name = m_dev.group(1).strip()
                full_path = f"{current_path}.{dev_name}".replace("\\.", "\\")
                self.devices.setdefault(dev_name, []).append((dev_name, full_path))

    def _detect_cpu_scope(self, text: str) -> None:
        # Look for _PR or CPU scope
        m = re.search(r"Scope\s+\((\\_PR|_PR)\)", text)
        if m:
            self.cpu_scope = m.group(1)
            return

        m = re.search(r"Scope\s+\((\\_SB\.PR00|\\_SB\.PR01)\)", text)
        if m:
            self.cpu_scope = m.group(1)

    def _detect_timers(self, text: str) -> None:
        if "Device (AWAC)" in text or "OperationRegion (AWAC" in text:
            self.has_awac = True
        if "Device (RTC" in text or "OperationRegion (RTC" in text:
            self.has_rtc = True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _write_and_compile(self, out_dir: Path, name: str, dsl: str) -> None:
        dsl_path = out_dir / f"{name}.dsl"
        aml_path = out_dir / f"{name}.aml"

        dsl_path.write_text(dsl, encoding="utf-8")
        cmd = [self.iasl_path, dsl_path.name]
        subprocess.run(cmd, cwd=out_dir, check=True)

        if not aml_path.exists():
            raise RuntimeError(f"Failed to compile {name}.dsl to AML")

    def _find_device_path(self, candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in self.devices:
                # Return first occurrence
                return self.devices[c][0][1]
        return None

    # ------------------------------------------------------------------ #
    # SSDT-EC
    # ------------------------------------------------------------------ #

    def _gen_ssdt_ec(self, out_dir: Path) -> None:
        ec_path = self._find_device_path(["EC", "EC0", "H_EC", "ECDV"])
        if not ec_path:
            ec_path = "\\_SB.PCI0.LPCB.EC"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "EC", 0x00000000)
{{
    External ({ec_path}, DeviceObj)

    Scope ({ec_path.rsplit('.', 1)[0]})
    {{
        Device (EC)
        {{
            Name (_HID, "PNP0C09")
            Name (_UID, 1)
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-EC", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-PLUG
    # ------------------------------------------------------------------ #

    def _gen_ssdt_plug(self, out_dir: Path) -> None:
        cpu_scope = self.cpu_scope or "\\_PR"
        cpu0_path = f"{cpu_scope}.CPU0" if "CPU0" in (self.devices.keys()) else f"{cpu_scope}.PR00"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "PLUG", 0x00000000)
{{
    External ({cpu0_path}, DeviceObj)

    Scope ({cpu_scope})
    {{
        Device (PLUG)
        {{
            Name (_HID, "ACPI000C")
            Name (_CID, "ACPI000C")
            Name (_UID, 0x00)
            Method (_STA, 0, NotSerialized)
            {{
                Return (0x0F)
            }}
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-PLUG", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-USBX
    # ------------------------------------------------------------------ #

    def _gen_ssdt_usbx(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "USBX", 0x00000000)
{
    Device (USBX)
    {
        Name (_ADR, Zero)
        Method (_DSM, 4, NotSerialized)
        {
            If (!Arg2)
            {
                Return (Buffer() { 0x03 })
            }

            Return (Package ()
            {
                "kUSBSleepPowerSupply", 0x13,
                "kUSBSleepPortCurrentLimit", 0x0834,
                "kUSBWakePowerSupply", 0x13,
                "kUSBWakePortCurrentLimit", 0x0834
            })
        }
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-USBX", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-PNLF
    # ------------------------------------------------------------------ #

    def _gen_ssdt_pnlf(self, out_dir: Path) -> None:
        igpu_path = self._find_device_path(["IGPU", "GFX0", "VID", "GPU0"]) or "\\_SB.PCI0.IGPU"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "PNLF", 0x00000000)
{{
    External ({igpu_path}, DeviceObj)

    Device (PNLF)
    {{
        Name (_HID, "APP0002")
        Name (_CID, "APP0002")
        Name (_UID, 0x0A)
        Name (_STA, 0x0B)
        Method (_DSM, 4, NotSerialized)
        {{
            If (!Arg2)
            {{
                Return (Buffer() {{ 0x03 }})
            }}

            Return (Package ()
            {{
                "AAPL,backlight-control", One
            }})
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-PNLF", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-AWAC
    # ------------------------------------------------------------------ #

    def _gen_ssdt_awac(self, out_dir: Path) -> None:
        if not self.has_awac:
            # Still generate as requested, but generic
            pass

        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "AWAC", 0x00000000)
{
    Scope (\)
    {
        If (_OSI ("Darwin"))
        {
            If (CondRefOf (\_SB.AWAC))
            {
                Store (One, \_SB.AWAC.DIS0)
            }
        }
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-AWAC", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-HPET
    # ------------------------------------------------------------------ #

    def _gen_ssdt_hpet(self, out_dir: Path) -> None:
        hpet_path = self._find_device_path(["HPET"]) or "\\_SB.PCI0.LPCB.HPET"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "HPET", 0x00000000)
{{
    External ({hpet_path}, DeviceObj)

    Scope ({hpet_path.rsplit('.', 1)[0]})
    {{
        Device (HPET)
        {{
            Name (_HID, "PNP0103")
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-HPET", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-SBUS
    # ------------------------------------------------------------------ #

    def _gen_ssdt_sbus(self, out_dir: Path) -> None:
        sbus_path = self._find_device_path(["SBUS", "SMBS"]) or "\\_SB.PCI0.SBUS"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "SBUS", 0x00000000)
{{
    External ({sbus_path}, DeviceObj)

    Scope ({sbus_path.rsplit('.', 1)[0]})
    {{
        Device (SBUS)
        {{
            Name (_HID, "PNP0C02")
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-SBUS", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-XOSI
    # ------------------------------------------------------------------ #

    def _gen_ssdt_xosi(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "XOSI", 0x00000000)
{
    Method (XOSI, 1, NotSerialized)
    {
        If (Arg0 == "Windows 2009")
        {
            Return (One)
        }
        If (Arg0 == "Darwin")
        {
            Return (One)
        }
        Return (Zero)
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-XOSI", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-IMEI
    # ------------------------------------------------------------------ #

    def _gen_ssdt_imei(self, out_dir: Path) -> None:
        imei_path = self._find_device_path(["IMEI", "HECI"]) or "\\_SB.PCI0.IMEI"

        dsl = f"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "IMEI", 0x00000000)
{{
    External ({imei_path}, DeviceObj)

    Scope ({imei_path.rsplit('.', 1)[0]})
    {{
        Device (IMEI)
        {{
            Name (_HID, "INT33A1")
        }}
    }}
}}
"""
        self._write_and_compile(out_dir, "SSDT-IMEI", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-RTC0
    # ------------------------------------------------------------------ #

    def _gen_ssdt_rtc0(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "RTC0", 0x00000000)
{
    Device (RTC0)
    {
        Name (_HID, "PNP0B00")
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-RTC0", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-ALS0
    # ------------------------------------------------------------------ #

    def _gen_ssdt_als0(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "ALS0", 0x00000000)
{
    Device (ALS0)
    {
        Name (_HID, "ACPI0008")
        Name (_CID, "smc-als")
        Name (_UID, 0x01)
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-ALS0", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-GPRW
    # ------------------------------------------------------------------ #

    def _gen_ssdt_gprw(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "GPRW", 0x00000000)
{
    Method (GPRW, 2, NotSerialized)
    {
        Return (Package ()
        {
            0x09,
            0x04
        })
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-GPRW", dsl)

    # ------------------------------------------------------------------ #
    # SSDT-USB-Reset
    # ------------------------------------------------------------------ #

    def _gen_ssdt_usb_reset(self, out_dir: Path) -> None:
        dsl = r"""
DefinitionBlock ("", "SSDT", 2, "OCPROJ", "USB-RST", 0x00000000)
{
    Device (URST)
    {
        Name (_HID, "ACPI000E")
    }
}
"""
        self._write_and_compile(out_dir, "SSDT-USB-Reset", dsl)
