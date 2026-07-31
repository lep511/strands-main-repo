"""CPU information detection and display utility."""

import multiprocessing
import platform

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def get_cpu_info() -> dict:
    """Gather CPU information from the system.

    Returns a dictionary with processor details. Uses psutil for extended
    info when available, falls back to standard library otherwise.
    """
    info: dict = {
        "processor": platform.processor() or platform.machine(),
        "architecture": platform.machine(),
        "system": platform.system(),
        "logical_cores": multiprocessing.cpu_count(),
        "physical_cores": None,
        "frequency": None,
    }

    if _HAS_PSUTIL:
        info["physical_cores"] = psutil.cpu_count(logical=False)
        freq = psutil.cpu_freq()
        if freq:
            info["frequency"] = {
                "current": round(freq.current, 2),
                "min": round(freq.min, 2),
                "max": round(freq.max, 2),
            }

    return info


def display_cpu_info(info: dict) -> None:
    """Print CPU information in a human-readable format."""
    print("=" * 40)
    print("        CPU Information")
    print("=" * 40)
    print(f"  Processor:      {info['processor']}")
    print(f"  Architecture:   {info['architecture']}")
    print(f"  System:         {info['system']}")
    print(f"  Logical Cores:  {info['logical_cores']}")

    if info["physical_cores"] is not None:
        print(f"  Physical Cores: {info['physical_cores']}")
    else:
        print("  Physical Cores: N/A (install psutil for this info)")

    if info["frequency"] is not None:
        freq = info["frequency"]
        print(f"  Frequency:      {freq['current']} MHz")
        if freq["min"] > 0:
            print(f"  Freq Range:     {freq['min']} - {freq['max']} MHz")
    else:
        print("  Frequency:      N/A (install psutil for this info)")

    print("=" * 40)


def main() -> None:
    """Entry point for the CPU info script."""
    info = get_cpu_info()
    display_cpu_info(info)


if __name__ == "__main__":
    main()
