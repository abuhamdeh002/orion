import logging
import urllib.parse
import webbrowser
from typing import Literal, Optional

from pydantic import BaseModel

from tools.base_tool import BaseTool, ToolResult
from core.permissions import RiskLevel

logger = logging.getLogger("orion.tools.browser")

class BrowserArgs(BaseModel):
    action: Literal["open", "search"]
    url: Optional[str] = None
    query: Optional[str] = None

class BrowserTool(BaseTool):
    name = "browser"
    description = "Open a URL in the default browser or perform a web search."
    risk = RiskLevel.LOW
    input_schema = BrowserArgs
    
    def __init__(self, search_url_template: str = "https://duckduckgo.com/?q={query}"):
        super().__init__()
        self.search_url_template = search_url_template
        
    def execute(self, arguments: BaseModel | dict) -> ToolResult:
        if isinstance(arguments, dict):
            try:
                args = BrowserArgs(**arguments)
            except Exception as e:
                return ToolResult(ok=False, message=f"Invalid arguments: {e}")
        elif isinstance(arguments, BrowserArgs):
            args = arguments
        else:
            return ToolResult(ok=False, message="Invalid arguments type.")

        if args.action == "open":
            if not args.url:
                return ToolResult(ok=False, message="URL is required when action is 'open'.")
            
            parsed = urllib.parse.urlparse(args.url)
            scheme = parsed.scheme.lower()
            
            if scheme not in ["http", "https"]:
                return ToolResult(ok=False, message=f"Invalid or unsupported URL scheme: '{scheme}'. Only http and https are allowed.")
                
            try:
                webbrowser.open(args.url)
                logger.info(f"Opened URL: {args.url}")
                return ToolResult(ok=True, message=f"Opened {args.url}", data={"url": args.url})
            except Exception as e:
                logger.error(f"Failed to open URL: {e}")
                return ToolResult(ok=False, message=f"Failed to open URL: {str(e)}")
                
        elif args.action == "search":
            if not args.query:
                return ToolResult(ok=False, message="Query is required when action is 'search'.")
                
            query_encoded = urllib.parse.quote_plus(args.query)
            search_url = self.search_url_template.format(query=query_encoded)
            
            try:
                webbrowser.open(search_url)
                logger.info(f"Searched for: {args.query}")
                return ToolResult(ok=True, message=f"Performed search for '{args.query}'", data={"url": search_url})
            except Exception as e:
                logger.error(f"Failed to open search: {e}")
                return ToolResult(ok=False, message=f"Failed to perform search: {str(e)}")
