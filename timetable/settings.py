from dataclasses import dataclass, field
from typing import Annotated

import click
import typer

from .hour import Hour, HourParamType


NOTHING = object()


class CommaSeparatedParamType(click.ParamType):
    """
    Provide a custom `click` type for comma-separated values.
    """

    name = "value1,value2,..."

    def convert(self, value, param, ctx):
        """Converts the value from string into hour type."""
        return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class _SettingsBase:
    """Base class that is used for the settings and for the CLI options."""

    title_height: float = 15
    title_shadow: bool = False
    hours_width: float | None = None
    wrap_hour: Annotated[Hour, typer.Option(click_type=HourParamType())] = None  # type: ignore
    day_height: float = 10
    show_weeks: bool = True
    show_teacher: bool = True
    show_room: bool = True
    show_first_last: bool = True
    show_pause: bool = True
    black_white: bool = False
    render_real_hours: bool = False
    no_styles: bool = False
    tags: Annotated[str, typer.Option(click_type=CommaSeparatedParamType())] = ""
    no_tags: Annotated[str, typer.Option(click_type=CommaSeparatedParamType())] = ""

    @classmethod
    def merge(cls, *objs: "_SettingsBase"):
        """
        Merge two `Setting` objects. Settings specified later will override the other ones.

        >>> Settings.merge(Settings(title_shadow=True), Settings(title_shadow=False))  # doctest: +ELLIPSIS
        Settings(..., title_shadow=False, ...)
        """
        kwargs = {}

        for name in cls.__dataclass_fields__:
            value = NOTHING
            for obj in objs[::-1]:
                # Handle nonexistent keys and None values
                if obj.__dict__.get(name) != cls.__dict__.get(name):
                    value = obj.__dict__.get(name)
                    break
            if value is not NOTHING:
                kwargs[name] = value

        return cls(**kwargs)


@dataclass
class Settings(_SettingsBase):
    """Settings for the timetable renderer."""
    colors: dict = field(default_factory=dict)
    real_hours: dict = field(default_factory=dict)


app = typer.Typer()


@dataclass
class _SettingsBase2:
    """Wrapper for the `timetable_paths` setting."""

    timetable_paths: list[str]


@app.command()
@dataclass
class CLI(_SettingsBase, _SettingsBase2):
    """CLI settings."""

    output: str = "%(timetables)s.pdf"
    open: bool = False

    def __post_init__(self):
        from . import real_main

        real_main(self)


@dataclass
class _SettingsBase3:
    """Wrapper for the `timetable_files` setting."""

    timetable_files: list[typer.FileText]


@dataclass
class WebSettings(_SettingsBase, _SettingsBase3):
    """Web settings."""

    output: str = "%(timetables)s.pdf"
