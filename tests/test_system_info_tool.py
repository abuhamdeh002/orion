import pytest
from unittest.mock import patch, MagicMock

from tools.system_info_tool import SystemInfoTool, SystemInfoArgs
from pydantic import ValidationError

@pytest.fixture
def tool():
    return SystemInfoTool()

@patch("tools.system_info_tool.psutil")
def test_battery_with_value(mock_psutil, tool):
    mock_battery = MagicMock()
    mock_battery.percent = 85
    mock_battery.power_plugged = True
    mock_battery.secsleft = 3600
    mock_psutil.sensors_battery.return_value = mock_battery
    mock_psutil.POWER_TIME_UNKNOWN = -1
    mock_psutil.POWER_TIME_UNLIMITED = -2
    
    result = tool.execute({"category": "battery"})
    assert result.ok
    assert result.data["battery"]["percent"] == "85%"
    assert result.data["battery"]["is_charging"] is True
    assert result.data["battery"]["time_remaining_mins"] == 60

@patch("tools.system_info_tool.psutil")
def test_battery_none_desktop(mock_psutil, tool):
    mock_psutil.sensors_battery.return_value = None
    
    result = tool.execute({"category": "battery"})
    assert result.ok
    assert result.data["battery"]["status"] == "no battery"

@patch("tools.system_info_tool.psutil")
def test_cpu_query(mock_psutil, tool):
    mock_psutil.cpu_percent.return_value = 15.5
    mock_psutil.cpu_count.side_effect = [8, 4]
    mock_freq = MagicMock()
    mock_freq.current = 2400
    mock_psutil.cpu_freq.return_value = mock_freq
    
    result = tool.execute({"category": "cpu"})
    assert result.ok
    assert result.data["cpu"]["usage"] == "15.5%"
    assert result.data["cpu"]["cores_logical"] == 8
    assert result.data["cpu"]["cores_physical"] == 4
    assert result.data["cpu"]["frequency_mhz"] == 2400

@patch("tools.system_info_tool.psutil")
def test_memory_query(mock_psutil, tool):
    mock_mem = MagicMock()
    mock_mem.total = 16 * (1024**3)
    mock_mem.available = 8 * (1024**3)
    mock_mem.percent = 50.0
    mock_psutil.virtual_memory.return_value = mock_mem
    
    result = tool.execute({"category": "memory"})
    assert result.ok
    assert result.data["memory"]["total"] == "16.0 GB"
    assert result.data["memory"]["available"] == "8.0 GB"
    assert result.data["memory"]["percent"] == "50.0%"

@patch("tools.system_info_tool.psutil")
def test_disk_query(mock_psutil, tool):
    mock_disk = MagicMock()
    mock_disk.total = 500 * (1024**3)
    mock_disk.used = 250 * (1024**3)
    mock_disk.free = 250 * (1024**3)
    mock_disk.percent = 50.0
    mock_psutil.disk_usage.return_value = mock_disk
    
    result = tool.execute({"category": "disk"})
    assert result.ok
    assert result.data["disk"]["total"] == "500.0 GB"
    assert result.data["disk"]["used"] == "250.0 GB"
    assert result.data["disk"]["free"] == "250.0 GB"
    assert result.data["disk"]["percent"] == "50.0%"
    mock_psutil.disk_usage.assert_called_once_with("C:\\")

@patch("tools.system_info_tool.socket.socket")
def test_network_connectivity_success(mock_socket_cls, tool):
    mock_sock = MagicMock()
    mock_socket_cls.return_value = mock_sock
    
    result = tool.execute({"category": "network"})
    assert result.ok
    assert result.data["network"]["connected"] is True
    mock_sock.connect.assert_called_once_with(("8.8.8.8", 53))

@patch("tools.system_info_tool.socket.socket")
def test_network_connectivity_failure(mock_socket_cls, tool):
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = Exception("Network down")
    mock_socket_cls.return_value = mock_sock
    
    result = tool.execute({"category": "network"})
    assert result.ok
    assert result.data["network"]["connected"] is False
    assert "Network down" in result.data["network"]["error"]

@patch("tools.system_info_tool.psutil")
@patch("tools.system_info_tool.socket.socket")
def test_all_query(mock_socket, mock_psutil, tool):
    result = tool.execute({"category": "all"})
    assert result.ok
    assert "battery" in result.data
    assert "cpu" in result.data
    assert "memory" in result.data
    assert "disk" in result.data
    assert "network" in result.data

def test_invalid_category_handled_by_schema():
    with pytest.raises(ValidationError):
        SystemInfoArgs(category="invalid")

@patch("tools.system_info_tool.psutil")
def test_disk_access_denied(mock_psutil, tool):
    mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
    mock_psutil.disk_usage.side_effect = mock_psutil.AccessDenied("Access denied")
    
    result = tool.execute({"category": "disk"})
    assert result.ok
    assert result.data["disk"]["error"] == "Access denied"
