from unittest.mock import patch
import cpu_info


def test_get_cpu_info_returns_dict():
    result = cpu_info.get_cpu_info()
    assert isinstance(result, dict)


def test_cpu_info_has_processor():
    result = cpu_info.get_cpu_info()
    assert "processor" in result
    assert isinstance(result["processor"], str)


def test_cpu_info_has_architecture():
    result = cpu_info.get_cpu_info()
    assert "architecture" in result
    assert isinstance(result["architecture"], str)
    assert len(result["architecture"]) > 0


def test_cpu_info_has_logical_cores():
    result = cpu_info.get_cpu_info()
    assert "logical_cores" in result
    assert isinstance(result["logical_cores"], int)
    assert result["logical_cores"] > 0


def test_cpu_info_has_physical_cores():
    result = cpu_info.get_cpu_info()
    assert "physical_cores" in result
    value = result["physical_cores"]
    assert value is None or (isinstance(value, int) and value > 0)


def test_cpu_info_has_frequency():
    result = cpu_info.get_cpu_info()
    assert "frequency" in result
    value = result["frequency"]
    if value is not None:
        assert isinstance(value, dict)
        assert "current" in value


def test_display_cpu_info_runs_without_error(capsys):
    info = cpu_info.get_cpu_info()
    cpu_info.display_cpu_info(info)
    captured = capsys.readouterr()
    assert "Processor" in captured.out or "Architecture" in captured.out


def test_graceful_without_psutil():
    with patch.dict("sys.modules", {"psutil": None}):
        import importlib
        importlib.reload(cpu_info)
        result = cpu_info.get_cpu_info()
        assert isinstance(result, dict)
        assert "logical_cores" in result
    importlib.reload(cpu_info)


def test_main_runs(capsys):
    cpu_info.main()
    captured = capsys.readouterr()
    assert len(captured.out) > 0
