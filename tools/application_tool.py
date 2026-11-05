import logging
import subprocess
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("orion.tools.app_launcher")

class AppLaunchArgs(BaseModel):
    app_name: str = Field(min_length=1, description="Name/alias of the application to launch")

class ApplicationTool(BaseTool):
    name: str = "app_launcher"
    description: str = "Open an application from the approved allowlist."
    risk: RiskLevel = RiskLevel.MEDIUM
    requires_confirmation: bool = True
    
    def __init__(self, allowed_apps: list[Any] | None = None) -> None:
        self._allowed_apps: dict[str, str] = {}
        if allowed_apps:
            for item in allowed_apps:
                if isinstance(item, (tuple, list)):
                    self.add_app(item[0], item[1])
                elif hasattr(item, "alias") and hasattr(item, "path"):
                    self.add_app(item.alias, item.path)
                
    @property
    def input_schema(self) -> type[BaseModel]:
        return AppLaunchArgs
        
    def add_app(self, alias: str, path: str) -> None:
        self._allowed_apps[alias.lower()] = path
        
    def list_apps(self) -> list[str]:
        return sorted(self._allowed_apps.keys())
        
    def execute(self, arguments: BaseModel | dict) -> ToolResult:
        if isinstance(arguments, dict):
            try:
                arguments = AppLaunchArgs(**arguments)
            except Exception as e:
                return ToolResult(ok=False, message=f"Invalid arguments: {e}")
        elif not isinstance(arguments, AppLaunchArgs):
            return ToolResult(ok=False, message="Invalid arguments type.")
            
        app_name = arguments.app_name.lower()
        
        if app_name not in self._allowed_apps:
            available = self.list_apps()
            return ToolResult(
                ok=False, 
                message=f"'{app_name}' is not in the allowed applications list. Available: {available}"
            )
            
        app_path = Path(self._allowed_apps[app_name])
        
        if not app_path.exists():
            return ToolResult(ok=False, message=f"Path does not exist for '{app_name}'")
            
        try:
            subprocess.Popen([str(app_path)], shell=False)
            logger.info(f"Launched application '{app_name}' from {app_path}")
            return ToolResult(
                ok=True, 
                message=f"Successfully launched '{app_name}'.", 
                data={"app_name": app_name, "path": str(app_path)}
            )
        except OSError as e:
            logger.error(f"Failed to launch '{app_name}': {e}")
            return ToolResult(ok=False, message=f"Failed to launch '{app_name}': {e}")
