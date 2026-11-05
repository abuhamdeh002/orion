import pytest
from unittest.mock import patch
from pydantic import ValidationError

from tools.application_tool import ApplicationTool, AppLaunchArgs

def test_add_and_list_apps():
    tool = ApplicationTool(allowed_apps=[("Calc", "C:\\Windows\\System32\\calc.exe")])
    tool.add_app("Notepad", "C:\\Windows\\System32\\notepad.exe")
    apps = tool.list_apps()
    assert apps == ["calc", "notepad"]

@patch("tools.application_tool.Path.exists")
@patch("tools.application_tool.subprocess.Popen")
def test_launch_known_app_success(mock_popen, mock_exists):
    mock_exists.return_value = True
    tool = ApplicationTool(allowed_apps=[("notepad", "C:\\Windows\\System32\\notepad.exe")])
    
    args = AppLaunchArgs(app_name="NOTEPAD")
    result = tool.execute(args)
    
    assert result.ok is True
    assert result.message == "Successfully launched 'notepad'."
    assert result.data == {"app_name": "notepad", "path": "C:\\Windows\\System32\\notepad.exe"}
    
    mock_popen.assert_called_once_with(["C:\\Windows\\System32\\notepad.exe"], shell=False)

def test_launch_unknown_app_returns_error():
    tool = ApplicationTool(allowed_apps=[("notepad", "C:\\Windows\\System32\\notepad.exe")])
    
    args = AppLaunchArgs(app_name="calculator")
    result = tool.execute(args)
    
    assert result.ok is False
    assert "'calculator' is not in the allowed applications list. Available: ['notepad']" in result.message

@patch("tools.application_tool.Path.exists")
def test_launch_app_non_existent_path(mock_exists):
    mock_exists.return_value = False
    tool = ApplicationTool(allowed_apps=[("notepad", "C:\\Windows\\System32\\notepad.exe")])
    
    args = AppLaunchArgs(app_name="notepad")
    result = tool.execute(args)
    
    assert result.ok is False
    assert "Path does not exist" in result.message

def test_empty_app_name_rejected_by_schema():
    with pytest.raises(ValidationError):
        AppLaunchArgs(app_name="")

@patch("tools.application_tool.Path.exists")
@patch("tools.application_tool.subprocess.Popen")
def test_subprocess_oserror_returns_ok_false(mock_popen, mock_exists):
    mock_exists.return_value = True
    mock_popen.side_effect = OSError("Access denied")
    tool = ApplicationTool(allowed_apps=[("notepad", "C:\\Windows\\System32\\notepad.exe")])
    
    args = AppLaunchArgs(app_name="notepad")
    result = tool.execute(args)
    
    assert result.ok is False
    assert "Failed to launch 'notepad': Access denied" in result.message

@patch("tools.application_tool.Path.exists")
@patch("tools.application_tool.subprocess.Popen")
def test_subprocess_shell_is_false(mock_popen, mock_exists):
    mock_exists.return_value = True
    tool = ApplicationTool(allowed_apps=[("notepad", "C:\\Windows\\System32\\notepad.exe")])
    
    args = AppLaunchArgs(app_name="notepad")
    tool.execute(args)
    
    mock_popen.assert_called_once_with(["C:\\Windows\\System32\\notepad.exe"], shell=False)
