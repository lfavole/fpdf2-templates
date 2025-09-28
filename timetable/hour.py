from functools import total_ordering
from typing import Literal, Self

import click


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

        # If we are given an already created hour instance (like in __add__),
        # immediatly set the total and abort
        if isinstance(hour, type(self)):
            self.total = hour.total
            return

        # If we want to directly set the total, set it and abort
        if minute is True:
            if not isinstance(hour, (int, float)):
                raise TypeError("Trying to create an Hour instance from a total but the total is not an int/float")
            self.total = int(hour % (24 * 60))
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
        return int(self // interval) * type(self)(interval)

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

    def difference(self: Self, other: Self | str | float):
        """
        Return the difference between this hour and the other hour.

        >>> Hour(8, 30).difference(Hour(8, 0))
        Hour(0, 30)
        >>> Hour(8, 0).difference(Hour(8, 30))
        Hour(0, 30)
        """
        other = type(self)(other)
        return self - other if self > other else other - self

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
        Hour(4, 0)
        >>> Hour(8, 0) / Hour(2, 0)
        4
        >>> Hour(8, 0) / 3
        Hour(2, 40)
        """
        if isinstance(other, type(self)):
            return self.total / other.total
        # Don't convert immediately to hours (1 != Hour(1).total)
        if isinstance(other, (int, float)):
            return Hour(self.total / other, True)
        return Hour(self.total / type(self)(other).total, True)

    __rtruediv__ = __itruediv__ = __truediv__

    def __floordiv__(self: Self, other: Self | str | float):
        """
        >>> Hour(8, 0) // 2
        Hour(4, 0)
        >>> Hour(8, 0) // Hour(2, 0)
        4
        >>> Hour(8, 0) // 3
        Hour(2, 0)
        >>> Hour(8, 0) // Hour(3, 0)
        2
        """
        if isinstance(other, type(self)):
            return self.total // other.total
        # Don't convert immediately to hours (1 != Hour(1).total)
        if isinstance(other, (int, float)):
            return Hour(self.total // other, True)
        return Hour(self.total // type(self)(other).total, True)

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

    def human_repr(self):
        """
        >>> str(Hour(8, 0))
        '8h'
        >>> str(Hour(8, 5))
        '8h05'
        >>> str(Hour(8, 30))
        '8h30'
        """
        return f"{self.hour}h" + (f"{self.minute:02d}" if self.minute else "")

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
