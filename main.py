import os
import sys
import time
from typing import Any, Dict

from hardware_detection import HardwareDetector
from compatibility_checker import CompatibilityChecker
from efi_builder import EFIBuilder

APP_NAME = "OpenCore Prodigy"
APP_VERSION = "0.4.0"


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg: str = "Press Enter to continue...") -> None:
    try:
        input(msg)
    except KeyboardInterrupt:
        sys.exit(0)


def print_header(title: str = "") -> None:
    clear_screen()
    print("=" * 60)
    print(f"{APP_NAME} v{APP_VERSION}".center(60))
    print("=" * 60)
    if title:
        print(f"{title}\n")


def detect_hardware() -> Dict[str, Any]:
    print_header("Detecting Hardware")
    detector = HardwareDetector()
    report = detector.get_hardware_report()

    print("Hardware detection complete.\n")
    print("Summary:\n")

    cpu = report.get("CPU", {})
    print(f"CPU: {cpu.get('Processor Name')} ({cpu.get('Cores')} cores / {cpu.get('Threads')} threads)")

    gpus = report.get("GPU", {})
    for name, gpu in gpus.items():
        print(f"GPU: {name} ({gpu.get('Manufacturer')})")

    board = report.get("Motherboard", {})
    print(f"Motherboard: {board.get('Name')} ({board.get('Manufacturer')})")

    print("\nFull hardware report saved in memory.")
    pause()
    return report


def run_compatibility_check(hardware_report: Dict[str, Any]) -> Dict[str, Any]:
    print_header("Checking macOS Compatibility")
    checker = CompatibilityChecker()
    hw, (min_native, max_native), ocl_patched = checker.check_compatibility(hardware_report)

    summary = {
        "min_native": min_native,
        "max_native": max_native,
        "ocl_patched": ocl_patched,
    }

    print("\nCompatibility summary:\n")
    print(f"  Native macOS range : {min_native} → {max_native}")
    if ocl_patched:
        print("  OCLP patches      : Required for newer versions")
    else:
        print("  OCLP patches      : Not required for supported range")

    pause()
    return summary


def download_dependencies(target_dir: str) -> None:
    print_header("Download / Cache Information")

    print(f"Cache directory:\n  {os.path.join(os.getcwd(), 'Cache')}\n")
    print("The EFI builder will download and cache:")
    print("  - OpenCore (latest stable)")
    print("  - Kexts (extended universal set)")
    print("  - Drivers")
    print("  - Tools (including acpidump.exe)")
    print("\nDownloads happen automatically during EFI build and are reused on future runs.")
    pause()


def build_efi(hardware_report: Dict[str, Any],
              compatibility_report: Dict[str, Any],
              output_dir: str) -> None:
    print_header("Building EFI")

    builder = EFIBuilder(base_dir=os.getcwd())
    builder.build_efi(hardware_report, compatibility_report, output_dir)

    pause("EFI build finished. Press Enter to return to the menu...")


def ensure_output_dir() -> str:
    default_dir = os.path.join(os.getcwd(), "EFI_Output")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def main_menu() -> None:
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
