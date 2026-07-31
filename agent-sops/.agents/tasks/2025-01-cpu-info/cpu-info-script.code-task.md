# Task: Create CPU Info Script

## Description
Create a Python script `cpu_info.py` that detects and displays detailed information about the system's processor. This script will provide users with a quick and easy way to identify the CPU type and relevant hardware specifications of their machine.

## Background
Knowing the processor type and its characteristics is essential for system diagnostics, performance tuning, and compatibility checks. Python provides built-in and third-party libraries to retrieve this information in a cross-platform way.

## Reference Documentation
**Required:**
- N/A (standalone script, no design document required)

**Additional References (if relevant to this task):**
- Python `platform` module docs: https://docs.python.org/3/library/platform.html
- Python `cpuinfo` library: https://pypi.org/project/py-cpuinfo/

**Note:** Review the Python standard library documentation for cross-platform CPU detection before implementation.

## Technical Requirements
1. Create a file named `cpu_info.py` at the root of the project
2. Use Python's built-in `platform` and `os` modules as primary source of CPU information
3. Optionally use the `py-cpuinfo` third-party library for extended details
4. Display at minimum: processor name/type, architecture, number of cores (physical and logical), and CPU frequency
5. The script must run on Windows, macOS, and Linux without modification
6. Output must be human-readable and clearly labeled

## Dependencies
- Python 3.7+
- Built-in modules: `platform`, `os`, `multiprocessing`
- Optional third-party: `psutil` (for frequency and core count), `py-cpuinfo` (for detailed CPU brand string)

## Implementation Approach
1. Import `platform`, `os`, and `multiprocessing` from the standard library
2. Use `platform.processor()` and `platform.machine()` to get basic CPU info
3. Use `multiprocessing.cpu_count()` for logical core count
4. Optionally import `psutil` to retrieve CPU frequency and physical core count
5. Format and print all gathered information in a clean, labeled output
6. Handle import errors gracefully if optional libraries are not installed

## Acceptance Criteria

1. **Basic CPU Information Display**
   - Given the script is executed on any supported OS
   - When `python cpu_info.py` is run
   - Then the processor name/type and architecture are printed to the console

2. **Core Count Detection**
   - Given the script is running on a multi-core system
   - When the script executes
   - Then both logical and physical core counts are displayed (if available)

3. **CPU Frequency**
   - Given `psutil` is installed
   - When the script executes
   - Then the current, minimum, and maximum CPU frequencies are displayed in MHz/GHz

4. **Graceful Degradation**
   - Given `psutil` or `py-cpuinfo` is NOT installed
   - When the script executes
   - Then it falls back to standard library data and displays a note about missing optional libraries

5. **Cross-Platform Compatibility**
   - Given the script is run on Windows, macOS, or Linux
   - When executed with Python 3.7+
   - Then it produces valid output on all three platforms without errors

6. **Unit Test Coverage**
   - Given the cpu_info implementation
   - When running the test suite
   - Then all information-gathering functions have corresponding unit tests with >90% coverage

## Metadata
- **Complexity**: Low
- **Labels**: Python, System Info, CPU, Cross-Platform, Utility Script
- **Required Skills**: Python standard library, system programming basics, optional dependency handling
