# Context: CPU Info Script

## Project Structure
- **Type**: Python project (uv-managed, pyproject.toml)
- **Python Version**: >=3.13
- **Repo Root**: /home/ssm-user/strands-main-repo/agent-sops
- **Test Framework**: To be created with pytest (standard for Python projects)

## Requirements

From the code task file:

1. Create `cpu_info.py` at project root
2. Use built-in `platform`, `os`, `multiprocessing` modules
3. Optionally use `psutil` for frequency/core count, `py-cpuinfo` for brand string
4. Display: processor name/type, architecture, cores (physical + logical), CPU frequency
5. Cross-platform (Windows, macOS, Linux)
6. Human-readable, clearly labeled output
7. Graceful degradation when optional libraries unavailable

## Patterns

- Project uses `uv` for dependency management
- Source code under `src/agent_sops/`
- Entry point defined in pyproject.toml

## Implementation Path

- Script: `cpu_info.py` (project root)
- Tests: `tests/test_cpu_info.py`

## Dependencies

- Built-in: `platform`, `os`, `multiprocessing`
- Optional: `psutil` (frequency, physical cores)
