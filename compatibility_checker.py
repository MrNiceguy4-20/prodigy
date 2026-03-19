import re
from typing import Any, Dict, Tuple, Optional


class CompatibilityChecker:
    """
    Hackintosh‑friendly macOS compatibility engine.
    Produces:
      - Native macOS range
      - OCLP macOS range
      - Recommended macOS version (balanced mode)
      - GPU acceleration warnings
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def check_compatibility(
        self, hardware: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Tuple[str, str], bool]:
        """
        Returns:
          hardware (unchanged),
          (min_native, max_native),
          oclp_required (bool)
        """

        cpu_info = hardware.get("CPU", {})
        gpu_info = hardware.get("GPU", {})
        form_factor = hardware.get("FormFactor", "Desktop")

        cpu_gen = self._detect_cpu_generation(cpu_info)
        cpu_vendor = self._detect_cpu_vendor(cpu_info)

        gpu_family, gpu_limit, gpu_accel_warning = self._detect_gpu_family_and_limit(gpu_info)

        native_min, native_max = self._cpu_native_range(cpu_vendor, cpu_gen)
        patched_min, patched_max = self._cpu_patched_range(cpu_vendor, cpu_gen)

        # GPU may lower the max version
        if gpu_limit is not None:
            native_max = self._min_version(native_max, gpu_limit)
            patched_max = self._min_version(patched_max, gpu_limit)

        # Determine if OCLP is required
        oclp_required = self._needs_oclp(cpu_vendor, cpu_gen, native_max, patched_max)

        # Balanced recommendation
        recommended = self._recommend_version(
            native_max=native_max,
            patched_max=patched_max,
            oclp_required=oclp_required,
            gpu_accel_warning=gpu_accel_warning,
            form_factor=form_factor,
            gpu_family=gpu_family,
        )

        hardware["Compatibility"] = {
            "CPU_Generation": cpu_gen,
            "CPU_Vendor": cpu_vendor,
            "GPU_Family": gpu_family,
            "NativeRange": (native_min, native_max),
            "PatchedRange": (patched_min, patched_max),
            "Recommended": recommended,
            "NeedsOCLP": oclp_required,
            "GPUAccelerationWarning": gpu_accel_warning,
        }

        return hardware, (native_min, native_max), oclp_required

    # ------------------------------------------------------------------ #
    # CPU detection
    # ------------------------------------------------------------------ #

    def _detect_cpu_vendor(self, cpu: Dict[str, Any]) -> str:
        name = (cpu.get("Processor Name") or "").lower()
        if "intel" in name:
            return "Intel"
        if "amd" in name or "ryzen" in name or "threadripper" in name:
            return "AMD"
        return "Unknown"

    def _detect_cpu_generation(self, cpu: Dict[str, Any]) -> Optional[int]:
        """
        Extract Intel CPU generation from model name.
        Example: "Intel(R) Core(TM) i7-8700K" -> 8th gen
        """
        name = cpu.get("Processor Name", "")
        match = re.search(r"i[3579]-([0-9]{4,5})", name)
        if not match:
            return None

        model = int(match.group(1))

        # 5-digit models (10th gen+): 10400, 11400, 12400, etc.
        if model >= 10000:
            return int(str(model)[0:2])  # 10th, 11th, 12th, 13th, 14th gen

        # 4-digit models: 2500, 3770, 4790, 6700, etc.
        return int(str(model)[0])  # 2nd–9th gen

    # ------------------------------------------------------------------ #
    # GPU detection
    # ------------------------------------------------------------------ #

    def _detect_gpu_family_and_limit(
        self, gpus: Dict[str, Dict[str, Any]]
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Returns:
          gpu_family (string),
          gpu_limit (max macOS version),
          gpu_accel_warning (string or None)
        """

        if not gpus:
            return "Unknown", None, None

        # Use the first GPU for compatibility
        gpu = list(gpus.values())[0]
        name = (gpu.get("Name") or "").lower()

        # Intel iGPU
        if "hd graphics 3000" in name:
            return "Intel HD 3000", "High Sierra", None
        if "hd graphics 4000" in name:
            return "Intel HD 4000", "Ventura", None
        if "uhd" in name or "iris" in name or "630" in name:
            return "Intel UHD/Iris", "Sonoma", None

        # NVIDIA
        if "gtx" in name or "rtx" in name or "quadro" in name:
            if any(k in name for k in ["750", "950", "960", "970", "980", "1050", "1060", "1070", "1080"]):
                return (
                    "NVIDIA Maxwell/Pascal",
                    "High Sierra",
                    "No hardware acceleration on macOS Mojave or newer.",
                )
            if any(k in name for k in ["640", "650", "660", "670", "680", "690", "710", "720", "730", "740"]):
                return "NVIDIA Kepler", "Monterey", None

        # AMD
        if "rx" in name:
            if any(k in name for k in ["460", "470", "480", "560", "570", "580"]):
                return "AMD Polaris", "Sonoma", None
            if any(k in name for k in ["5500", "5600", "5700"]):
                return "AMD Navi", "Sonoma", None
            if any(k in name for k in ["6600", "6700", "6800", "6900"]):
                return (
                    "AMD RDNA2",
                    "Sonoma",
                    "Requires OCLP for full acceleration.",
                )

        return "Unknown", None, None

    # ------------------------------------------------------------------ #
    # CPU → macOS ranges
    # ------------------------------------------------------------------ #

    def _cpu_native_range(self, vendor: str, gen: Optional[int]) -> Tuple[str, str]:
        if vendor == "AMD":
            return "High Sierra", "Sonoma"

        if gen is None:
            return "High Sierra", "Sonoma"

        if gen == 2:
            return "Lion", "High Sierra"
        if gen == 3:
            return "Mountain Lion", "Mojave"
        if gen == 4:
            return "Mavericks", "Big Sur"
        if gen == 5:
            return "Yosemite", "Monterey"
        if gen == 6:
            return "El Capitan", "Monterey"
        if gen == 7:
            return "Sierra", "Ventura"
        if gen == 8 or gen == 9:
            return "High Sierra", "Sonoma"
        if gen == 10:
            return "Mojave", "Sonoma"
        if gen == 11:
            return "Catalina", "Sonoma"
        if gen >= 12:
            return "Monterey", "Monterey"  # Native support ends here

        return "High Sierra", "Sonoma"

    def _cpu_patched_range(self, vendor: str, gen: Optional[int]) -> Tuple[str, str]:
        if vendor == "AMD":
            return "High Sierra", "Sonoma"

        if gen is None:
            return "High Sierra", "Sonoma"

        if gen in (2, 3):
            return "High Sierra", "Ventura"
        if gen == 4:
            return "High Sierra", "Sonoma"
        if gen in (5, 6, 7):
            return "High Sierra", "Sonoma"
        if gen >= 8:
            return "High Sierra", "Sonoma"

        return "High Sierra", "Sonoma"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _min_version(self, v1: str, v2: Optional[str]) -> str:
        if v2 is None:
            return v1
        versions = [
            "Lion",
            "Mountain Lion",
            "Mavericks",
            "Yosemite",
            "El Capitan",
            "Sierra",
            "High Sierra",
            "Mojave",
            "Catalina",
            "Big Sur",
            "Monterey",
            "Ventura",
            "Sonoma",
        ]
        return versions[min(versions.index(v1), versions.index(v2))]

    def _needs_oclp(self, vendor: str, gen: Optional[int], native_max: str, patched_max: str) -> bool:
        if vendor == "AMD":
            return True
        return native_max != patched_max

    # ------------------------------------------------------------------ #
    # Recommendation engine (Balanced Mode)
    # ------------------------------------------------------------------ #

    def _recommend_version(
        self,
        native_max: str,
        patched_max: str,
        oclp_required: bool,
        gpu_accel_warning: Optional[str],
        form_factor: str,
        gpu_family: str,
    ) -> str:
        """
        Balanced mode:
          - Prefer newest native version
          - If OCLP needed, recommend newest patched version *only if GPU supports it*
          - Avoid versions with broken acceleration
        """

        # If GPU acceleration breaks on newer macOS, recommend the last version with acceleration
        if gpu_accel_warning:
            return native_max

        # If native support exists, recommend newest native
        if not oclp_required:
            return native_max

        # If OCLP required, recommend newest patched version
        return patched_max
