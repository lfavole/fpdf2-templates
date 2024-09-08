import json
import sys
import tempfile
from functools import wraps
from pathlib import Path
from typing import Callable

import requests
from fpdf import FPDF


def patch_output_method(pdf: FPDF, callback: Callable[[], None]):
    """Set a callback to be run after the `output()` metod of a PDF is called."""
    old_output = pdf.output

    @wraps(old_output)
    def output(*args, **kwargs):
        ret = old_output(*args, **kwargs)
        callback()
        return ret

    pdf.output = output  # type: ignore
    return pdf


def get_path_to_font(font_name: str, font_style="Regular", pdf: FPDF | None = None):
    """Return the path to a font. If the font is not installed, download it from Google Fonts."""
    fonts_dir = Path("C:/Windows/Fonts") if sys.platform == "win32" else Path("/usr/share/fonts")
    font_filename = f"{font_name}-{font_style}.ttf"
    font_file = fonts_dir / font_filename
    if font_file.exists():
        return font_file

    resp = requests.get("https://fonts.google.com/download/list", {"family": font_name})
    data = json.loads(resp.text.lstrip(")]}'"))
    for file in data["manifest"]["fileRefs"]:
        if file["filename"].removeprefix("static/") == font_filename:
            resp = requests.get(file["url"], stream=True)
            with tempfile.NamedTemporaryFile("wb", suffix=Path(file["filename"]).suffix, delete=False) as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)
                if pdf:
                    patch_output_method(pdf, Path(f.name).unlink)
                return f.name

    return None


def add_font(pdf: FPDF, font_name: str, font_style="all"):
    if font_style == "all":
        add_font(pdf, font_name, "Regular")
        add_font(pdf, font_name, "Bold")
        add_font(pdf, font_name, "Italic")
        add_font(pdf, font_name, "BoldItalic")
        return

    font_path = get_path_to_font(font_name, font_style, pdf)
    if font_path:
        pdf.add_font(
            font_name,
            {
                "Regular": "",
                "Bold": "B",
                "Italic": "I",
                "BoldItalic": "BI",
            }[font_style],  # type: ignore
            font_path,
        )
    else:
        raise RuntimeError(f"Unable to find font: {font_name}-{font_style}")
