import logging
from datetime import datetime
from typing import Optional
import zoneinfo

from pydantic import BaseModel, Field

from tools.base_tool import BaseTool, ToolResult
from core.permissions import RiskLevel

logger = logging.getLogger("orion.tools.time_date")

class TimeArgs(BaseModel):
    query: str = Field(
        default="both",
        description="What the user wants: 'time', 'date', 'both', or 'datetime'"
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Optional IANA timezone like 'America/New_York'"
    )

class TimeDateTool(BaseTool):
    name: str = "time_date"
    description: str = "Get current local time, date, or both. Supports timezone-aware output."
    risk: RiskLevel = RiskLevel.LOW
    input_schema: type[BaseModel] = TimeArgs

    def execute(self, arguments: BaseModel | dict | None = None, **kwargs) -> ToolResult:
        if arguments is None and kwargs:
            arguments = kwargs
        if isinstance(arguments, TimeArgs):
            args = arguments
        elif isinstance(arguments, dict):
            try:
                args = TimeArgs(**arguments)
            except Exception as e:
                logger.error(f"Validation error: {e}")
                return ToolResult(ok=False, message=f"Invalid input: {e}")
        elif arguments is None:
            args = TimeArgs()
        else:
            return ToolResult(ok=False, message="Invalid arguments type.")

        tz = None
        if args.timezone:
            try:
                tz = zoneinfo.ZoneInfo(args.timezone)
            except Exception as e:
                logger.error(f"Invalid timezone {args.timezone}: {e}")
                return ToolResult(ok=False, message=f"Invalid timezone: {args.timezone}")

        now = datetime.now(tz=tz)
        
        data = {
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
            "timezone": str(tz) if tz else "local",
            "day_of_week": now.strftime("%A")
        }

        # Format message based on query
        q = args.query.lower()
        if q == "time":
            msg = f"Current time is {data['time']}"
            if tz:
                msg += f" in {data['timezone']}"
        elif q == "date":
            msg = f"Current date is {data['date']}"
        else:
            msg = f"Current date and time is {data['datetime']}"

        return ToolResult(ok=True, message=msg, data=data)
