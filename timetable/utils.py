import enum
from dataclasses import dataclass, field
from functools import total_ordering
import itertools
from typing import Annotated, Iterable, Literal, Protocol, Self, TypeVar

import click
import typer
from fpdf.drawing import DeviceRGB

_AddT = TypeVar("_AddT")


class SupportsAddAndComparison(Protocol[_AddT]):
    """A type that can be used in additions and comparisons."""

    def __add__(self, __x: _AddT) -> _AddT: ...
    def __lt__(self, __other: _AddT) -> bool: ...
    def __gt__(self, __other: _AddT) -> bool: ...


_T = TypeVar("_T", bound=SupportsAddAndComparison)


def range_any(start: _T, end: _T | None = None, interval=1, include_end=False) -> Iterable[_T]:
    """
    This function is like `range()`, but supports `start`, `end` and `interval` being of any type.

    >>> [*range_any(5)]
    [0, 1, 2, 3, 4]
    >>> [*range_any(5, include_end=True)]
    [0, 1, 2, 3, 4, 5]
    >>> [round(x, 6) for x in range_any(0, 1, 0.1)]
    [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    >>> [*range_any(Hour(3))]
    Traceback (most recent call last):
        ...
    TypeError: '<' not supported between instances of 'Hour' and 'int'
    >>> [*range_any(Hour(0), Hour(3))]
    [Hour(0, 0), Hour(1, 0), Hour(2, 0)]
    >>> [*range_any(Hour(0), Hour(3), include_end=True)]
    [Hour(0, 0), Hour(1, 0), Hour(2, 0), Hour(3, 0)]
    >>> [*range_any(Hour(0), Hour(6), 2)]
    [Hour(0, 0), Hour(2, 0), Hour(4, 0)]
    """
    if end is None:
        start, end = 0, start  # type: ignore
    reverse = end < start
    current = start
    ok_with_abs = all(isinstance(item, (int, float)) for item in (start, end, interval)) and not all(
        isinstance(item, int) for item in (start, end, interval)
    )
    while (
        ((current - end) if reverse else (end - current)) > 1e-6  # type: ignore
        if ok_with_abs
        else (current > end) if reverse else (current < end)
    ):
        yield current
        current += interval
    if include_end:
        yield current


@total_ordering
class Hour:
    """
    The representation of an hour (or an interval between two hours, e.g. 1 hour step).

    Note: `Hour` objects are immutable and support hour/minute/day overflow.

    >>> Hour(12, 60)
    Hour(13, 0)
    >>> Hour(23, 60)
    Hour(0, 0)
    >>> Hour(24, 0)
    Hour(0, 0)
    """

    def __init__(self: Self, hour: Self | str | float = 0, minute: float | Literal[True] = 0):
        """
        Create an `Hour` instance.

        To create an `Hour` instance from a total, you can use `Hour(total, True)`.
        """
        self.total = 0

        # If we want to directly set the total, set it and abort
        if minute is True:
            if not isinstance(hour, (int, float)):
                raise TypeError("Trying to create an Hour instance from a total but the total is not an int/float")
            self.total = int(hour % (24 * 60))
            return

        # If we are given an already created hour instance (like in __add__),
        # immediatly set the total and abort
        if isinstance(hour, type(self)):
            if minute:
                raise TypeError("You mustn't specify the minutes argument if you give an Hour instance for hours")
            self.total = hour.total
            return

        # If we have a string, parse it
        if isinstance(hour, str):
            if minute:
                raise TypeError("You mustn't specify the minutes argument if you give a string for hours")
            parts = hour.split(":", 1)
            if len(parts) < 2:
                parts = hour.split("h", 1)
            if len(parts) < 2:
                raise ValueError(f"No ':' or 'h' in hour string: {hour!r}")
            hour = float(parts[0] or "")
            minute = float(parts[1] or "")

        self.total += hour * 60
        self.total += minute
        self.total = int(self.total % (24 * 60))  # type: ignore

    @property
    def hour(self):
        """
        The number of hours.

        >>> Hour(8, 30).hour
        8
        >>> Hour(-1).hour
        23
        >>> Hour(25).hour
        1
        """
        return self.total // 60

    @property
    def minute(self):
        """
        The number of minutes.

        >>> Hour(8, 30).minute
        30
        >>> Hour(8, 61).minute
        1
        >>> Hour(8, -1).minute
        59
        """
        return self.total % 60

    def floor(self: Self, interval: Self | str | float = 1):
        """
        Clamp down the hour to the given interval.

        >>> Hour(8, 30).floor()
        Hour(8, 0)
        >>> Hour(8, 0).floor()
        Hour(8, 0)
        >>> Hour(9, 30).floor(2)
        Hour(8, 0)
        >>> Hour(9, 0).floor(2)
        Hour(8, 0)
        """
        return self // interval * type(self)(interval)

    def ceil(self: Self, interval: Self | str | float = 1):
        """
        Clamp up the hour to the given interval.

        >>> Hour(8, 30).ceil()
        Hour(9, 0)
        >>> Hour(8, 0).ceil()
        Hour(8, 0)
        >>> Hour(8, 30).ceil(2)
        Hour(10, 0)
        >>> Hour(9, 0).ceil(2)
        Hour(10, 0)
        """
        interval = type(self)(interval)
        return self.floor(interval) + (0 if (self % interval).total == 0 else interval)

    def __add__(self: Self, other: Self | str | float):
        """
        >>> Hour(8, 0) + Hour(1, 30)
        Hour(9, 30)
        >>> Hour(23, 59) + Hour(0, 2)
        Hour(0, 1)
        """
        return type(self)(self.total + type(self)(other).total, True)

    __radd__ = __iadd__ = __add__

    def __sub__(self: Self, other: Self | str | float):
        """
        >>> Hour(12, 0) - Hour(1, 30)
        Hour(10, 30)
        >>> Hour(0, 1) - Hour(0, 2)
        Hour(23, 59)
        """
        return type(self)(self.total - type(self)(other).total, True)

    __rsub__ = __isub__ = __sub__

    def __mul__(self: Self, other: float):
        """
        >>> Hour(8, 0) * 2
        Hour(16, 0)
        >>> Hour(12, 0) * 2
        Hour(0, 0)
        >>> Hour(12, 1) * 2
        Hour(0, 2)
        """
        return type(self)(self.total * other, True)

    __rmul__ = __imul__ = __mul__

    def __truediv__(self: Self, other: Self | str | float):
        """
        >>> Hour(8, 0) / 2
        4.0
        >>> round(Hour(8, 0) / 3, 3)
        2.667
        """
        return self.total / type(self)(other).total

    __rtruediv__ = __itruediv__ = __truediv__

    def __floordiv__(self: Self, other: Self | str | float):
        """
        >>> Hour(8, 0) // 2
        4
        >>> Hour(8, 0) // 3
        2
        """
        return self.total // type(self)(other).total

    __rfloordiv__ = __ifloordiv__ = __floordiv__

    def __mod__(self: Self, other: Self | str | float):
        """
        >>> Hour(8, 0) % 2
        Hour(0, 0)
        >>> Hour(9, 0) % 2
        Hour(1, 0)
        """
        return type(self)(self.total % type(self)(other).total, True)

    __rmod__ = __imod__ = __mod__

    def __pos__(self):
        """
        >>> +Hour(8, 0)
        480
        """
        return self.total

    def __neg__(self):
        """
        >>> -Hour(8, 0)
        Hour(16, 0)
        >>> -Hour(16, 0)
        Hour(8, 0)
        >>> -Hour(0, 0)
        Hour(0, 0)
        """
        return type(self)(-self.total, True)

    def __int__(self):
        """
        >>> int(Hour(8, 0))
        8
        """
        return self.hour

    def __float__(self):
        """
        >>> float(Hour(8, 0))
        8.0
        >>> float(Hour(8, 30))
        8.5
        """
        return self.total / 60

    def __lt__(self, other):
        """
        >>> Hour(8, 0) < Hour(8, 30)
        True
        >>> Hour(23, 59) < Hour(24, 0)
        False
        >>> Hour(0, -1) < Hour(0, 0)
        False
        """
        if isinstance(other, type(self)):
            return self.total < other.total
        return NotImplemented

    def __eq__(self, other):
        """
        >>> Hour(8, 0) == Hour(8, 0)
        True
        >>> Hour(8, 0) == Hour(8, 30)
        False
        """
        if isinstance(other, type(self)):
            return self.total == other.total
        return NotImplemented

    def __hash__(self):
        return self.total

    def __str__(self):
        """
        >>> str(Hour(8, 0))
        '8:00'
        >>> str(Hour(8, 30))
        '8:30'
        """
        return f"{self.hour}:{self.minute:02d}"

    def __repr__(self):
        """
        >>> repr(Hour(8, 0))
        'Hour(8, 0)'
        >>> repr(Hour(8, 30))
        'Hour(8, 30)'
        """
        return f"Hour({self.hour}, {self.minute})"


class HourParamType(click.ParamType):
    """
    Provide a custom `click` type for hours.
    """

    name = "Hour"

    def convert(self, value, param, ctx):
        """Converts the value from string into hour type."""
        try:
            return Hour(value)
        except ValueError as e:
            self.fail(f"Not a valid hour: {e}", param, ctx)


class Week(enum.IntEnum):
    """Week type: every week, on left weeks or on right weeks."""

    ALWAYS = 0
    LEFT = 1
    RIGHT = 2


@dataclass
class Lesson:
    """A lesson in a timetable."""

    start: "Hour"
    end: "Hour"
    name: str
    teacher: str
    room: int | str = ""
    color: str | DeviceRGB | None = None
    week: Week = Week.ALWAYS
    removed: bool = False

    def __post_init__(self):
        if isinstance(self.color, str) and len(self.color) == 7 and self.color[0] == "#":
            try:
                self.color = DeviceRGB(
                    int(self.color[1:3], 16) / 255,
                    int(self.color[3:5], 16) / 255,
                    int(self.color[5:7], 16) / 255,
                    None,
                )
            except ValueError:
                pass

        self.room = str(self.room)


@dataclass
class Day:
    """A day in a timetable."""

    name: str
    lessons: list[Lesson] = field(default_factory=list)

    def __iter__(self):
        return iter(self.lessons)


@dataclass
class Timetable:
    """A timetable."""

    title: str = "Timetable"
    days: list[Day] = field(default_factory=list)
    left_week: str = ""
    right_week: str = ""

    def __iter__(self):
        return iter(self.days)

    def __len__(self):
        return len(self.days)

    @classmethod
    def from_data(cls, data: str):
        """Create a timetable from data contained in a timetable file."""

        # Avoid circular imports
        from .tt_parser import TimetableParser

        return TimetableParser(data).timetable


@dataclass
class Pause:
    """A pause (a range between two `Hour`s)."""
    start: Hour
    end: Hour

    @classmethod
    def intersection(cls, *pauses: Self) -> Self | None:
        """
        Return the longest `Pause` object that is contained into all the given `Pause`s
        or `None` if it doesn't exist.

        >>> Pause.intersection(Pause(Hour(8), Hour(17)), Pause(Hour(12), Hour(13)))
        Pause(start=Hour(12, 0), end=Hour(13, 0))
        >>> Pause.intersection(Pause(Hour(11), Hour(13)), Pause(Hour(12), Hour(14)))
        Pause(start=Hour(12, 0), end=Hour(13, 0))
        """
        # If there are no pauses, stop here to avoid further errors with max and min
        if not pauses:
            return None
        # Latest start hour
        start = max(*(pause.start for pause in pauses))
        # Earliest end hour
        end = min(*(pause.end for pause in pauses))
        # If a pause begins after another ends, it means there is no intersection
        if end < start:
            return None
        return cls(start, end)

    def __bool__(self):
        """
        Returns `True` if the pause is not empty (the start hour and end hour are different), `False` otherwise.

        >>> bool(Pause(Hour(12), Hour(13)))
        True
        >>> bool(Pause(Hour(13), Hour(13)))
        False
        """
        return self.start != self.end

    def __contains__(self, other: Self | Hour):
        """
        Returns `True` if the pause contains the given `Hour` or `Pause`, `False` otherwise.

        >>> Pause(Hour(8), Hour(9)) in Pause(Hour(8), Hour(9))
        True
        >>> Pause(Hour(8, 15), Hour(8, 45)) in Pause(Hour(8), Hour(9))
        True
        >>> Pause(Hour(8), Hour(10)) in Pause(Hour(8), Hour(9))
        False
        >>> Hour(8) in Pause(Hour(8), Hour(9))
        True
        >>> Hour(8, 30) in Pause(Hour(8), Hour(9))
        True
        >>> Hour(9) in Pause(Hour(8), Hour(9))
        True
        >>> Hour(10) in Pause(Hour(8), Hour(9))
        False
        """
        if isinstance(other, Hour):
            return self.start <= other <= self.end
        return self.start <= other.start and other.end <= self.end


@dataclass
class Pauses:
    """An object that holds the `Pause` objects for a day."""
    start: Hour
    end: Hour
    pauses: list[Pause] = field(default_factory=list)

    def __contains__(self, other: Hour | Pause):
        """
        Returns `True` if any pauses in the day contains the given `Hour` or `Pause`, `False` otherwise.

        >>> pauses = Pauses(Hour(8), Hour(17), [Pause(Hour(8), Hour(9)), Pause(Hour(16), Hour(17))])
        >>> Pause(Hour(8), Hour(9)) in pauses
        True
        >>> Pause(Hour(8, 15), Hour(8, 45)) in pauses
        True
        >>> Pause(Hour(8), Hour(10)) in pauses
        False
        >>> Hour(8) in pauses
        True
        >>> Hour(8, 30) in pauses
        True
        >>> Hour(9) in pauses
        True
        >>> Hour(10) in pauses
        False

        >>> # Empty Pauses objects
        >>> pauses = Pauses(Hour(8), Hour(17))
        >>> Hour(8) in pauses
        True
        >>> Pause(Hour(8), Hour(10)) in pauses
        True

        >>> # Pauses outside the day
        >>> pauses = Pauses(Hour(8), Hour(17), [Pause(Hour(12), Hour(13))])
        >>> Pause(Hour(6), Hour(7)) in pauses
        True
        >>> Pause(Hour(9), Hour(10)) in pauses
        False
        >>> Pause(Hour(17), Hour(18)) in pauses
        True
        """
        # If there are no pauses, it means that all the day is a pause
        # so that day contains all hours and pauses
        if not self.pauses:
            return True
        # If we are outside the day, it's a pause
        if isinstance(other, Pause):
            if other.end <= self.start or self.end <= other.start:
                return True
        else:
            if other <= self.start or self.end <= other:
                return True
        for pause in self.pauses:
            if other in pause:
                return True
        return False

    def __iter__(self):
        """
        Return an iterator on all the pauses on the current day:
        the specified pauses plus the implicit start and end pauses.

        >>> [*Pauses(Hour(8), Hour(17), [Pause(Hour(11), Hour(13))])]
        [Pause(start=Hour(0, 0), end=Hour(8, 0)), Pause(start=Hour(11, 0), end=Hour(13, 0)), Pause(start=Hour(17, 0), end=Hour(23, 59))]
        """
        return itertools.chain((Pause(Hour(0), self.start),), self.pauses, (Pause(self.end, Hour(-1, True)),))


@dataclass
class PausesContainer:
    """An object that holds a list of `Pauses` objects (pauses for each day)."""
    start_hour: Hour
    end_hour: Hour
    days: list[Pauses] = field(default_factory=list)

    def intersection(self):
        """
        Returns the pause that is common to all days or `None` if it doesn't exist.

        >>> container = PausesContainer(Hour(8), Hour(17))
        >>> start_of_day = Pause(Hour(0), Hour(8))
        >>> end_of_day = Pause(Hour(17), Hour(-1, True))
        >>> container.days.append(Pauses(Hour(8), Hour(17), [Pause(Hour(11), Hour(13))]))
        >>> container.days.append(Pauses(Hour(8), Hour(17), [Pause(Hour(12), Hour(14))]))
        >>> container.intersection()
        Pause(start=Hour(12, 0), end=Hour(13, 0))

        >>> # With smaller pauses
        >>> container.days.append(Pauses(Hour(8), Hour(17), [start_of_day, Pause(Hour(13), Hour(14)), end_of_day]))
        >>> container.intersection()

        >>> # Without intersection
        >>> container.days.append(Pauses(Hour(8), Hour(17), [start_of_day, Pause(Hour(11), Hour(12)), end_of_day]))
        >>> container.intersection()
        """
        # For all the combinations of pauses (all the ways to take one pause on each day)
        for pauses in itertools.product(*self.days):
            # If the pauses list is empty, all elements will have a length of 0 so we stop here
            if len(pauses) == 0:
                break
            # Calculate the intersection of all the pauses
            intersection = Pause.intersection(*pauses)
            # If there is an intersection (this excludes empty pauses)
            # and this intersection is within the day, return it
            if intersection and intersection in Pause(self.start_hour, self.end_hour):
                return intersection
        # There is no intersection, return None
        return None


NOTHING = object()


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
                if obj.__dict__.get(name) is not None:
                    value = obj.__dict__.get(name)
                    break
            if value is not NOTHING:
                kwargs[name] = value

        return cls(**kwargs)


@dataclass
class Settings(_SettingsBase):
    """Settings for the timetable renderer."""


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
