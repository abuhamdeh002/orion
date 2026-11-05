import pytest
from pydantic import ValidationError

from tools.time_tool import TimeDateTool, TimeArgs

def test_time_tool_basic():
    tool = TimeDateTool()
    result = tool.execute(query="time")
    assert result.ok is True
    assert "time" in result.data
    assert "date" in result.data
    assert "datetime" in result.data
    assert "timezone" in result.data
    assert "day_of_week" in result.data
    assert "Current time is" in result.message

def test_time_tool_date_query():
    tool = TimeDateTool()
    result = tool.execute(query="date")
    assert result.ok is True
    assert "Current date is" in result.message

def test_time_tool_both_query():
    tool = TimeDateTool()
    result = tool.execute(query="both")
    assert result.ok is True
    assert "Current date and time" in result.message

def test_time_tool_datetime_query():
    tool = TimeDateTool()
    result = tool.execute(query="datetime")
    assert result.ok is True
    assert "Current date and time" in result.message

def test_time_tool_default_query():
    tool = TimeDateTool()
    result = tool.execute()
    assert result.ok is True
    assert "Current date and time" in result.message

def test_time_tool_valid_timezone():
    tool = TimeDateTool()
    result = tool.execute(timezone="UTC")
    assert result.ok is True
    assert result.data["timezone"] == "UTC"
    assert "UTC" in result.data["datetime"]

def test_time_tool_invalid_timezone():
    tool = TimeDateTool()
    result = tool.execute(timezone="Invalid/Timezone")
    assert result.ok is False
    assert "Invalid timezone" in result.message

def test_time_args_validation():
    args = TimeArgs()
    assert args.query == "both"
    assert args.timezone is None
    
    args_valid = TimeArgs(query="time", timezone="UTC")
    assert args_valid.query == "time"
    assert args_valid.timezone == "UTC"
