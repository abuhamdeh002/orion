import logging
import socket
from typing import Literal

from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("orion.tools.system_info")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class SystemInfoArgs(BaseModel):
    category: Literal["battery", "cpu", "memory", "disk", "network", "all"] = Field(default="all")

def _format_bytes(bytes_val: int) -> str:
    try:
        gb = float(bytes_val) / (1024 ** 3)
        return f"{gb:.1f} GB"
    except Exception:
        return "unknown"

class SystemInfoTool(BaseTool):
    name = "system_info"
    description = "Read system information: battery, CPU, memory, disk, and network status."
    risk = RiskLevel.LOW
    input_schema = SystemInfoArgs

    def execute(self, arguments: BaseModel | dict | None = None) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(ok=False, message="psutil is not installed", data={})

        if isinstance(arguments, SystemInfoArgs):
            category = arguments.category
        elif isinstance(arguments, dict):
            category = arguments.get("category", "all")
        else:
            category = "all"

        data = {}

        if category in ("battery", "all"):
            data["battery"] = self._get_battery()
            
        if category in ("cpu", "all"):
            data["cpu"] = self._get_cpu()
            
        if category in ("memory", "all"):
            data["memory"] = self._get_memory()
            
        if category in ("disk", "all"):
            data["disk"] = self._get_disk()
            
        if category in ("network", "all"):
            data["network"] = self._get_network()

        return ToolResult(
            ok=True, 
            message=f"Successfully retrieved system info for category: {category}", 
            data=data
        )

    def _get_battery(self) -> dict:
        try:
            if not hasattr(psutil, "sensors_battery"):
                return {"status": "unsupported"}
            battery = psutil.sensors_battery()
            if battery is None:
                return {"status": "no battery"}
            
            time_remaining = battery.secsleft
            if time_remaining == psutil.POWER_TIME_UNKNOWN:
                time_str = "unknown"
            elif time_remaining == psutil.POWER_TIME_UNLIMITED:
                time_str = "unlimited"
            else:
                time_str = round(time_remaining / 60)

            return {
                "percent": f"{battery.percent}%",
                "is_charging": battery.power_plugged,
                "time_remaining_mins": time_str
            }
        except Exception as e:
            logger.error(f"Error reading battery: {e}")
            return {"error": str(e)}

    def _get_cpu(self) -> dict:
        try:
            freq = psutil.cpu_freq()
            return {
                "usage": f"{psutil.cpu_percent(interval=0.5)}%",
                "cores_logical": psutil.cpu_count(logical=True),
                "cores_physical": psutil.cpu_count(logical=False),
                "frequency_mhz": freq.current if freq else "unknown"
            }
        except Exception as e:
            logger.error(f"Error reading CPU: {e}")
            return {"error": str(e)}

    def _get_memory(self) -> dict:
        try:
            mem = psutil.virtual_memory()
            return {
                "total": _format_bytes(mem.total),
                "available": _format_bytes(mem.available),
                "percent": f"{mem.percent}%"
            }
        except Exception as e:
            logger.error(f"Error reading memory: {e}")
            return {"error": str(e)}

    def _get_disk(self) -> dict:
        try:
            # disk usage for C:\
            disk = psutil.disk_usage("C:\\")
            return {
                "total": _format_bytes(disk.total),
                "used": _format_bytes(disk.used),
                "free": _format_bytes(disk.free),
                "percent": f"{disk.percent}%"
            }
        except Exception as e:
            denied_cls = getattr(psutil, "AccessDenied", None)
            if (isinstance(denied_cls, type) and issubclass(denied_cls, BaseException) and isinstance(e, denied_cls)) or "AccessDenied" in type(e).__name__:
                logger.error("Access denied reading disk")
                return {"error": "Access denied"}
            logger.error(f"Error reading disk: {e}")
            return {"error": str(e)}

    def _get_network(self) -> dict:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect(("8.8.8.8", 53))
            sock.close()
            return {"connected": True}
        except Exception as e:
            logger.error(f"Error checking network: {e}")
            return {"connected": False, "error": str(e)}
