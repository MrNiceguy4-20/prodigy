import os
import sys
import time
from typing import Any, Dict

from hardware_detection import HardwareDetector
from compatibility_checker import CompatibilityChecker
from efi_builder import EFIBuilder

APP_NAME = "OpenCore Prodigy"
APP_VERSION = "0.4.1"  # bumped for improved build


def clear_screen() -> None:
    """Clear the terminal screen in a cross‑platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg: str = "Press Enter to continue...") -> None:
    """Pause execution until the user presses Enter, handling Ctrl+C gracefully."""
    try:
        input(msg)
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
        sys.exit(0)


def print_header(title: str = "") -> None:
    """Print a consistent application header with an optional section title."""
    clear_screen()
    print("=" * 60)
    print(f"{APP_NAME} v{APP_VERSION}".center(60))
    print("=" * 60)
    if title:
        print(f"{title}\n")


def detect_hardware() -> Dict[str, Any]:
    """Run hardware detection and return a structured report."""
    print_header("Detecting Hardware")
    detector = HardwareDetector()

    try:
        report = detector.get_hardware_report()
    except Exception as e:
        print(f"\nHardware detection failed: {e}\n")
        pause()
        return {}

    print("Hardware detection complete.\n")
    print("Summary:\n")

    cpu = report.get("CPU", {})
    if cpu:
        print(
            f"CPU: {cpu.get('Processor Name', 'Unknown')} "
            f"({cpu.get('Cores', '?')} cores / {cpu.get('Threads', '?')} threads)"
        )
    else:
        print("CPU: Unknown")

    gpus = report.get("GPU", {})
    if gpus:
        for name, gpu in gpus.items():
            print(f"GPU: {name} ({gpu.get('Manufacturer', 'Unknown')})")
    else:
        print("GPU: Unknown")

    board = report.get("Motherboard", {})
    if board:
        print(
            f"Motherboard: {board.get('Name', 'Unknown')} "
            f"({board.get('Manufacturer', board.get('SystemManufacturer', 'Unknown'))})"
        )
    else:
        print("Motherboard: Unknown")

    print("\nFull hardware report is kept in memory for later steps.")
    pause()
    return report


def run_compatibility_check(hardware_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run macOS compatibility analysis and return a rich summary.

    Returns a dict with:
      - min_native, max_native
      - ocl_patched (bool)
      - recommended (str)
      - native_range, patched_range
      - needs_oclp (bool)
      - gpu_family, gpu_accel_warning
    """
    print_header("Checking macOS Compatibility")

    checker = CompatibilityChecker()
    try:
        hw_with_compat, (min_native, max_native), ocl_patched = checker.check_compatibility(
            hardware_report
        )
    except Exception as e:
        print(f"\nCompatibility check failed: {e}\n")
        pause()
        return {}

    compat_section = hw_with_compat.get("Compatibility", {})

    summary: Dict[str, Any] = {
        "min_native": min_native,
        "max_native": max_native,
        "ocl_patched": ocl_patched,
        "recommended": compat_section.get("Recommended", max_native),
        "native_range": compat_section.get("NativeRange", (min_native, max_native)),
        "patched_range": compat_section.get("PatchedRange"),
        "needs_oclp": compat_section.get("NeedsOCLP", ocl_patched),
        "gpu_family": compat_section.get("GPU_Family"),
        "gpu_accel_warning": compat_section.get("GPUAccelerationWarning"),
    }

    print("\nCompatibility summary:\n")
    print(f" Native macOS range : {min_native} → {max_native}")
    if summary["patched_range"]:
        patched_min, patched_max = summary["patched_range"]
        print(f" Patched macOS range: {patched_min} → {patched_max}")

    if ocl_patched:
        print(" OCLP patches       : Required for newer versions")
    else:
        print(" OCLP patches       : Not required for supported range")

    if summary["gpu_family"]:
        print(f" GPU family         : {summary['gpu_family']}")
    if summary["gpu_accel_warning"]:
        print(f" GPU acceleration   : {summary['gpu_accel_warning']}")

    if summary["recommended"]:
        print(f"\n Recommended target : {summary['recommended']}")

    pause()
    return summary


def download_dependencies(target_dir: str) -> None:
    """Explain what will be downloaded and cached for EFI building."""
    print_header("Download / Cache Information")
    cache_dir = os.path.join(os.getcwd(), "Cache")
    print(f"Cache directory:\n {cache_dir}\n")
    print("The EFI builder will download and cache:")
    print(" - OpenCore (latest stable)")
    print(" - Kexts (extended universal set)")
    print(" - Drivers")
    print(" - Tools (including acpidump.exe)")
    print("\nDownloads happen automatically during EFI build and are reused on future runs.")
    pause()


def build_efi(
    hardware_report: Dict[str, Any],
    compatibility_report: Dict[str, Any],
    output_dir: str,
) -> None:
    """Invoke the EFI builder for the current machine."""
    print_header("Building EFI")
    builder = EFIBuilder(base_dir=os.getcwd())
    try:
        builder.build_efi(hardware_report, compatibility_report, output_dir)
    except Exception as e:
        print(f"\nEFI build failed: {e}\n")
        pause("Press Enter to return to the menu...")
        return

    pause("EFI build finished. Press Enter to return to the menu...")


def ensure_output_dir() -> str:
    """Ensure the default EFI output directory exists and return its path."""
    default_dir = os.path.join(os.getcwd(), "EFI_Output")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def main_menu() -> None:
    """Main interactive menu loop."""
    hardware_report: Dict[str, Any] = {}
    compatibility_report: Dict[str, Any] = {}

    while True:
        print_header("Main Menu")
        print("1. Detect hardware")
        print("2. Check macOS compatibility")
        print("3. View download/cache info")
        print("4. Build EFI for this machine")
        print("5. Exit\n")

        choice = input("Select an option: ").strip()

        if choice == "1":
            hardware_report = detect_hardware()

        elif choice == "2":
            if not hardware_report:
                print("\nNo hardware report found. Run 'Detect hardware' first.\n")
                pause()
                continue
            compatibility_report = run_compatibility_check(hardware_report)

        elif choice == "3":
            output_dir = ensure_output_dir()
            download_dependencies(output_dir)

        elif choice == "4":
            if not hardware_report:
                print("\nNo hardware report found. Run 'Detect hardware' first.\n")
                pause()
                continue
            if not compatibility_report:
                print("\nNo compatibility report found. Run 'Check macOS compatibility' first.\n")
                pause()
                continue

            output_dir = ensure_output_dir()
            build_efi(hardware_report, compatibility_report, output_dir)

        elif choice == "5":
            print("\nExiting. Goodbye.\n")
            time.sleep(0.3)
            sys.exit(0)

        else:
            print("\nInvalid choice.")
            pause()


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting.\n")
        sys.exit(0)
