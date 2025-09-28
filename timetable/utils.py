import enum
from typing import Iterable, Protocol, TypeVar

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


def min_or_none(*args):
    return _min_max_and_none(args, min)


def max_or_none(*args):
    return _min_max_and_none(args, max)


def _min_max_and_none(args, func):
    if len(args) == 1 and hasattr(args[0], "__iter__") and not isinstance(args[0], (str, bytes)):
        args = args[0]

    result = None
    for arg in args:
        if arg is None:
            continue
        result = arg if result is None else func(result, arg)
    return result


# Source: https://github.com/django/django/blob/be581ff4/django/utils/decorators.py#L8
class classonlymethod(classmethod):
    def __get__(self, instance, cls=None):
        if instance is not None:
            raise AttributeError("This method is available only on the class, not on instances.")
        return super().__get__(instance, cls)


class Week(enum.IntEnum):
    """Week type: every week, on left weeks or on right weeks."""

    ALWAYS = 0
    LEFT = 1
    RIGHT = 2
