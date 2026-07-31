# Plan: CPU Info Script

## Test Strategy

### Test Scenarios

1. **test_get_cpu_info_returns_dict** - Function returns a dictionary with expected keys
2. **test_cpu_info_has_processor_key** - Result includes processor name
3. **test_cpu_info_has_architecture_key** - Result includes architecture
4. **test_cpu_info_has_logical_cores** - Result includes logical core count as int > 0
5. **test_cpu_info_has_physical_cores** - Result includes physical cores (int or None)
6. **test_cpu_info_has_frequency** - Result includes frequency info (dict or None)
7. **test_display_cpu_info_runs_without_error** - Display function executes without exception
8. **test_graceful_without_psutil** - Module works when psutil is not available (mock import failure)
9. **test_main_runs** - Script's main block executes without error

### Test Framework
- pytest (add as dev dependency)

## Implementation Plan

### Architecture
- `get_cpu_info() -> dict` - Gathers all CPU info into a dictionary
- `display_cpu_info(info: dict) -> None` - Formats and prints the info
- `if __name__ == "__main__"` block to run as script

### Approach
1. Implement `get_cpu_info()` using platform/os/multiprocessing
2. Try importing psutil for extended info, handle ImportError
3. Implement `display_cpu_info()` for formatted output
4. Add main guard
