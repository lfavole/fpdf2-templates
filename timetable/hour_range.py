from dataclasses import dataclass
from typing import Self

from .hour import Hour
from .utils import classonlymethod


@dataclass
class HourRange:
    """A range between two `Hour`s. For example a pause."""
    start: Hour
    end: Hour

    @classonlymethod
    def intersection(cls, *hour_ranges: Self) -> Self | None:
        """
        Return the longest `HourRange` object that is contained into all the given `HourRange`s
        or `None` if it doesn't exist.

        >>> HourRange.intersection(HourRange(Hour(8), Hour(17)), HourRange(Hour(12), Hour(13)))
        HourRange(start=Hour(12, 0), end=Hour(13, 0))
        >>> HourRange.intersection(HourRange(Hour(11), Hour(13)), HourRange(Hour(12), Hour(14)))
        HourRange(start=Hour(12, 0), end=Hour(13, 0))
        """
        # If there are no hour ranges, stop here to avoid further errors with max and min
        if not hour_ranges:
            return None
        # Latest start hour
        start = max(hour_range.start for hour_range in hour_ranges)
        # Earliest end hour
        end = min(hour_range.end for hour_range in hour_ranges)
        # If a hour range begins after another ends, it means there is no intersection
        if end < start:
            return None
        return cls(start, end)

    def __bool__(self):
        """
        Returns `True` if the hour range is not empty (the start hour and end hour are different), `False` otherwise.

        >>> bool(HourRange(Hour(12), Hour(13)))
        True
        >>> bool(HourRange(Hour(13), Hour(13)))
        False
        """
        return self.start != self.end

    def __contains__(self, other: Self | Hour):
        """
        Returns `True` if the hour range contains the given `Hour` or `HourRange`, `False` otherwise.

        >>> HourRange(Hour(8), Hour(9)) in HourRange(Hour(8), Hour(9))
        True
        >>> HourRange(Hour(8, 15), Hour(8, 45)) in HourRange(Hour(8), Hour(9))
        True
        >>> HourRange(Hour(8), Hour(10)) in HourRange(Hour(8), Hour(9))
        False
        >>> Hour(8) in HourRange(Hour(8), Hour(9))
        True
        >>> Hour(8, 30) in HourRange(Hour(8), Hour(9))
        True
        >>> Hour(9) in HourRange(Hour(8), Hour(9))
        True
        >>> Hour(10) in HourRange(Hour(8), Hour(9))
        False
        """
        if isinstance(other, Hour):
            return self.start <= other <= self.end
        return self.start <= other.start and other.end <= self.end
