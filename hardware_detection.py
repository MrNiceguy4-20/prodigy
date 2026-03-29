import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional


def _ensure_wmi_installed() -> Optional[Any]:
    """
    Ensure the Python 'wmi' module is available on Windows.

    Returns the imported module or None if installation/import fails.
    """
    try:
        import wmi  # type: ignore

        return wmi
    except ImportError:
        print(" - Python 'wmi' module not found. Attempting installation with pip...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "wmi"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            print(" ! Failed to install 'wmi'. Hardware detection will be limited.")
            return None

        try:
            import wmi  # type: ignore

            return wmi
        except ImportError:
            print(" ! Still cannot import 'wmi'.")
            return None


class HardwareDetector:
    """
    Collects hardware information, primarily on Windows via WMI.

    On non‑Windows platforms or when WMI is unavailable, returns a minimal
    fallback report with OS info and placeholders for other sections.
    """

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"
        self.wmi = _ensure_wmi_installed() if self.is_windows else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_hardware_report(self) -> Dict[str, Any]:
        """Return a structured hardware report."""
        if not self.is_windows or self.wmi is None:
            return self._fallback_report()

        c = self.wmi.WMI()
        cpu = self._get_cpu_info(c)
        gpus = self._get_gpu_info(c)
        board = self._get_motherboard_info(c)
        ram = self._get_ram_info(c)
        storage = self._get_storage_info(c)
        network = self._get_network_info(c)
        battery = self._get_battery_info(c)
        is_laptop = self._infer_laptop(battery, board)

        report: Dict[str, Any] = {
            "OS": {
                "System": platform.system(),
                "Release": platform.release(),
                "Version": platform.version(),
                "Machine": platform.machine(),
            },
            "CPU": cpu,
            "GPU": gpus,
            "Motherboard": board,
            "RAM": ram,
            "Storage": storage,
            "Network": network,
            "Battery": battery,
            "FormFactor": "Laptop" if is_laptop else "Desktop",
        }
        return report

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def _get_cpu_info(self, c: Any) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        try:
            procs = c.Win32_Processor()
            if not procs:
                return info
            p = procs[0]
            info = {
                "Processor Name": getattr(p, "Name", "").strip(),
                "Manufacturer": getattr(p, "Manufacturer", "").strip(),
                "Cores": getattr(p, "NumberOfCores", None),
                "Threads": getattr(p, "NumberOfLogicalProcessors", None),
                "MaxClockMHz": getattr(p, "MaxClockSpeed", None),
                "Socket": getattr(p, "SocketDesignation", "").strip(),
                "Architecture": getattr(p, "Architecture", None),
            }
        except Exception:
            # Keep it silent but return whatever we have
            pass
        return info

    # ------------------------------------------------------------------
    # GPU
    # ------------------------------------------------------------------

    def _get_gpu_info(self, c: Any) -> Dict[str, Dict[str, Any]]:
        gpus: Dict[str, Dict[str, Any]] = {}
        try:
            adapters = c.Win32_VideoController()
            for idx, gpu in enumerate(adapters):
                name = getattr(gpu, "Name", f"GPU{idx}").strip()
                gpus[name] = {
                    "Name": name,
                    "Manufacturer": getattr(gpu, "AdapterCompatibility", "").strip(),
                    "VRAM_MB": int(getattr(gpu, "AdapterRAM", 0) or 0) // (1024 * 1024),
                    "DriverVersion": getattr(gpu, "DriverVersion", "").strip(),
                    "PNPDeviceID": getattr(gpu, "PNPDeviceID", "").strip(),
                }
        except Exception:
            pass
        return gpus

    # ------------------------------------------------------------------
    # Motherboard
    # ------------------------------------------------------------------

    def _get_motherboard_info(self, c: Any) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        try:
            boards = c.Win32_BaseBoard()
            if boards:
                b = boards[0]
                info["Manufacturer"] = getattr(b, "Manufacturer", "").strip()
                info["Product"] = getattr(b, "Product", "").strip()
                info["SerialNumber"] = getattr(b, "SerialNumber", "").strip()

            comps = c.Win32_ComputerSystem()
            if comps:
                cs = comps[0]
                info["Name"] = getattr(cs, "Model", "").strip()
                info["SystemManufacturer"] = getattr(cs, "Manufacturer", "").strip()
                info["ChassisType"] = getattr(cs, "PCSystemType", None)
        except Exception:
            pass
        return info

    # ------------------------------------------------------------------
    # RAM
    # ------------------------------------------------------------------

    def _get_ram_info(self, c: Any) -> Dict[str, Any]:
        info: Dict[str, Any] = {"TotalMB": None, "Modules": []}
        try:
            modules = c.Win32_PhysicalMemory()
            total = 0
            module_list: List[Dict[str, Any]] = []
            for m in modules:
                cap = int(getattr(m, "Capacity", 0) or 0)
                total += cap
                module_list.append(
                    {
                        "CapacityMB": cap // (1024 * 1024),
                        "SpeedMHz": getattr(m, "Speed", None),
                        "Manufacturer": getattr(m, "Manufacturer", "").strip(),
                        "PartNumber": getattr(m, "PartNumber", "").strip(),
                        "SerialNumber": getattr(m, "SerialNumber", "").strip(),
                    }
                )
            info["TotalMB"] = total // (1024 * 1024)
            info["Modules"] = module_list
        except Exception:
            pass
        return info

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _get_storage_info(self, c: Any) -> List[Dict[str, Any]]:
        drives: List[Dict[str, Any]] = []
        try:
            disks = c.Win32_DiskDrive()
            for d in disks:
                size = int(getattr(d, "Size", 0) or 0)
                drives.append(
                    {
                        "Model": getattr(d, "Model", "").strip(),
                        "InterfaceType": getattr(d, "InterfaceType", "").strip(),
                        "SizeGB": size // (1024 * 1024 * 1024),
                        "SerialNumber": getattr(d, "SerialNumber", "").strip(),
                        "MediaType": getattr(d, "MediaType", "").strip(),
                    }
                )
        except Exception:
            pass
        return drives

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def _get_network_info(self, c: Any) -> Dict[str, List[Dict[str, Any]]]:
        info: Dict[str, List[Dict[str, Any]]] = {"Ethernet": [], "WiFi": []}
        try:
            adapters = c.Win32_NetworkAdapter()
            for a in adapters:
                name = getattr(a, "Name", "").strip()
                pnp = getattr(a, "PNPDeviceID", "") or ""
                net_enabled = getattr(a, "NetEnabled", False)
                entry = {
                    "Name": name,
                    "Manufacturer": getattr(a, "Manufacturer", "").strip(),
                    "PNPDeviceID": pnp.strip(),
                    "NetEnabled": bool(net_enabled),
                }
                lname = name.lower()
                lpnp = pnp.lower()

                if (
                    "wireless" in lname
                    or "wi-fi" in lname
                    or "wifi" in lname
                    or "wlan" in lname
                ):
                    info["WiFi"].append(entry)
                elif "bluetooth" in lname or "bluetooth" in lpnp:
                    # ignore BT here; handled separately if needed
                    continue
                else:
                    info["Ethernet"].append(entry)
        except Exception:
            pass
        return info

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def _get_battery_info(self, c: Any) -> Dict[str, Any]:
        info: Dict[str, Any] = {"Present": False, "Batteries": []}
        try:
            bats = c.Win32_Battery()
            if bats:
                info["Present"] = True
                for b in bats:
                    info["Batteries"].append(
                        {
                            "Name": getattr(b, "Name", "").strip(),
                            "Status": getattr(b, "BatteryStatus", None),
                            "EstimatedChargeRemaining": getattr(
                                b, "EstimatedChargeRemaining", None
                            ),
                        }
                    )
        except Exception:
            pass
        return info

    # ------------------------------------------------------------------
    # Laptop vs Desktop heuristic
    # ------------------------------------------------------------------

    def _infer_laptop(self, battery: Dict[str, Any], board: Dict[str, Any]) -> bool:
        if battery.get("Present"):
            return True
        chassis = board.get("ChassisType")
        # PCSystemType: 2 = Mobile, 8 = Laptop, 9 = Notebook, 10 = Handheld, etc.
        if isinstance(chassis, int) and chassis in (2, 8, 9, 10, 11, 12, 14):
            return True
        return False

    # ------------------------------------------------------------------
    # Fallback (non‑Windows or no WMI)
    # ------------------------------------------------------------------

    def _fallback_report(self) -> Dict[str, Any]:
        """Return a minimal report when full WMI‑based detection is not available."""
        return {
            "OS": {
                "System": platform.system(),
                "Release": platform.release(),
                "Version": platform.version(),
                "Machine": platform.machine(),
            },
            "CPU": {},
            "GPU": {},
            "Motherboard": {},
            "RAM": {},
            "Storage": [],
            "Network": {"Ethernet": [], "WiFi": []},
            "Battery": {"Present": False, "Batteries": []},
            "FormFactor": "Unknown",
        }
