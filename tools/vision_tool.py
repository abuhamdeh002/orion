"""OCR and optional image description. Camera access is not performed here."""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.config import AppConfig
from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def _allowed_image(path: Path) -> bool:
    """Only image files under the user's own folders, ORION's data folder, or temp.

    The describe action uploads the file, so the model must not be able to point
    it at system files or arbitrary documents.
    """
    import tempfile

    from app.paths import app_data_dir

    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        return False
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    roots = [Path.home(), app_data_dir(), Path(tempfile.gettempdir())]
    return any(resolved.is_relative_to(root.resolve()) for root in roots)


class VisionArgs(BaseModel):
    action: Literal["ocr", "describe"]
    image_path: str = Field(min_length=1)


def _find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


class VisionTool(BaseTool):
    name = "vision"
    description = (
        "Read text from an image the user selected, or describe that image with a vision model. "
        "Never access the camera."
    )
    risk = RiskLevel.LOW

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def input_schema(self) -> type[BaseModel]:
        return VisionArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, VisionArgs):
            arguments = VisionArgs.model_validate(arguments)
        path = Path(arguments.image_path)
        if not path.is_file():
            return ToolResult(ok=False, message="That image file does not exist.")
        if not _allowed_image(path):
            return ToolResult(ok=False, message="I can only read image files from your own folders.")
        if arguments.action == "ocr":
            return self._ocr(path)
        return self._describe(path)

    def _ocr(self, path: Path) -> ToolResult:
        tesseract = _find_tesseract()
        if tesseract is None:
            return ToolResult(
                ok=False,
                message="Tesseract OCR is not installed. Install it and make sure it is on PATH.",
            )
        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            return ToolResult(ok=False, message="Pillow and pytesseract are required for OCR.")
        pytesseract.pytesseract.tesseract_cmd = tesseract
        try:
            text = pytesseract.image_to_string(Image.open(path)).strip()
        except Exception as exc:
            return ToolResult(ok=False, message=f"OCR failed: {exc}")
        if not text:
            return ToolResult(ok=True, message="No text was found in that image.", data={"text": ""})
        return ToolResult(ok=True, message=text, data={"text": text})

    def _describe(self, path: Path) -> ToolResult:
        if self.config.ai_provider != "openai" or not self.config.openai_api_key:
            return ToolResult(
                ok=False,
                message="Image description needs an OpenAI-compatible vision model and OPENAI_API_KEY.",
            )
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as exc:
            return ToolResult(ok=False, message=f"Could not read the image: {exc}")
        suffix = path.suffix.lower().lstrip(".") or "png"
        mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
        url = self.config.openai_base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.config.ai_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image briefly."},
                        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{encoded}"}},
                    ],
                }
            ],
            "max_tokens": 300,
        }
        try:
            with httpx.Client(timeout=self.config.request_timeout_seconds) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                    json=body,
                )
        except httpx.TimeoutException:
            return ToolResult(ok=False, message="The vision model timed out.")
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, message=f"Could not reach the vision model: {exc}")
        if response.status_code >= 400:
            return ToolResult(ok=False, message=f"Vision model error ({response.status_code}).")
        try:
            text = response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            return ToolResult(ok=False, message=f"Unexpected vision response: {exc}")
        return ToolResult(ok=True, message=text, data={"description": text})
