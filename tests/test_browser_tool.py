import pytest
from unittest.mock import patch
from pydantic import ValidationError

from tools.browser_tool import BrowserTool, BrowserArgs
from core.permissions import RiskLevel

@pytest.fixture
def browser_tool():
    return BrowserTool()

@patch('webbrowser.open')
def test_open_valid_https(mock_open, browser_tool):
    args = BrowserArgs(action="open", url="https://example.com")
    result = browser_tool.execute(args)
    assert result.ok is True
    assert result.data["url"] == "https://example.com"
    mock_open.assert_called_once_with("https://example.com")

@patch('webbrowser.open')
def test_open_valid_http(mock_open, browser_tool):
    args = BrowserArgs(action="open", url="http://example.com")
    result = browser_tool.execute(args)
    assert result.ok is True
    assert result.data["url"] == "http://example.com"
    mock_open.assert_called_once_with("http://example.com")

def test_open_javascript_rejected(browser_tool):
    args = BrowserArgs(action="open", url="javascript:alert(1)")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "scheme" in result.message.lower()

def test_open_file_rejected(browser_tool):
    args = BrowserArgs(action="open", url="file:///etc/passwd")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "scheme" in result.message.lower()

def test_open_empty_url_rejected(browser_tool):
    args = BrowserArgs(action="open", url="")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "url is required" in result.message.lower()

def test_open_no_url_rejected(browser_tool):
    args = BrowserArgs(action="open")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "url is required" in result.message.lower()

@patch('webbrowser.open')
def test_search_valid_query(mock_open, browser_tool):
    args = BrowserArgs(action="search", query="hello world")
    result = browser_tool.execute(args)
    assert result.ok is True
    expected_url = "https://duckduckgo.com/?q=hello+world"
    assert result.data["url"] == expected_url
    mock_open.assert_called_once_with(expected_url)

def test_search_empty_query_rejected(browser_tool):
    args = BrowserArgs(action="search", query="")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "query is required" in result.message.lower()

def test_search_no_query_rejected(browser_tool):
    args = BrowserArgs(action="search")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "query is required" in result.message.lower()

def test_schema_validation_action():
    with pytest.raises(ValidationError):
        BrowserArgs(action="invalid_action")

def test_open_no_scheme_rejected(browser_tool):
    args = BrowserArgs(action="open", url="example.com")
    result = browser_tool.execute(args)
    assert result.ok is False
    assert "scheme" in result.message.lower()
