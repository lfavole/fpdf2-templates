from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fpdf.enums import Align, StrokeCapStyle, XPos, YPos
from fpdf.fonts import FontFace

from .ctxvars import pdf, settings, timetable
from .hour import Hour
from .hour_range import HourRange
from .utils import max_or_none, min_or_none, range_any

if TYPE_CHECKING:
    from .timetable import Timetable


@dataclass
class HoursManager:
    """An object that manages the rendering of hours (at the left of the timetable)."""

    timetable: "Timetable"
    _hours_width: float | None = field(default=None, init=False)

    REAL_HOURS = object()

    @property
    def start(self):
        return min_or_none(day.start for day in timetable.days)

    @property
    def end(self):
        return max_or_none(day.end for day in timetable.days)

    @property
    def day_length(self):
        """
        The day length (end hour - start hour).

        >>> hours = HoursManager(TimetableRenderer(Timetable()))
        >>> hours.start
        >>> hours.end
        >>> hours.day_length
        Traceback (most recent call last):
        ...
        AssertionError: Attempt to use day_length on a timetable without hours

        >>> timetable = Timetable()
        >>> timetable.days.append(Day("..."))
        >>> timetable.days[0].lessons.extend([
        ...     Lesson(Hour(8), Hour(9), "", ""),
        ...     Lesson(Hour(16), Hour(17), "", ""),
        ... ])
        ...
        >>> renderer = TimetableRenderer(timetable)
        >>> renderer.hours.start
        Hour(8, 0)
        >>> renderer.hours.end
        Hour(17, 0)
        >>> renderer.hours.day_length
        Hour(9, 0)
        """
        assert (
            self.start is not None and self.end is not None
        ), "Attempt to use day_length on a timetable without hours"
        return self.end - self.start

    @property
    def width(self):
        """The width of the hours column (at the left of the timetable)."""
        if settings.hours_width:
            return settings.hours_width
        assert self._hours_width, "hours_width should have been filled"
        return self._hours_width

    def render(self, interval: "Hour | float | type[HoursManager.REAL_HOURS] | None" = None):
        """Render the hours (at the left of the timetable) with the given interval."""
        if self.start is None or self.end is None:
            assert self.start is None and self.end is None, "Only one of the hours is None"
            return
        if interval is None:
            interval = HoursManager.REAL_HOURS if settings.render_real_hours else 1
        if interval is self.REAL_HOURS:
            hours_set: set[Hour] = set()
            for day in timetable.days:
                for lesson in day.lessons:
                    hours_set.add(lesson.start)
                    hours_set.add(lesson.end)
            self.hours = sorted(hours_set)
        else:
            self.hours: list[Hour] = [
                *range_any(
                    self.start.ceil(interval),  # Start with the next hour (8:30 -> 9:00)...
                    self.end.floor(interval),  # ...and end with the previous hour (16:30 -> 16:00)
                    interval,  # type: ignore
                    include_end=True,
                )
            ]
        if not self.hours:
            # Stop here because getting the start and end hours will fail
            return
        self._hours_width = (
            max(pdf.get_string_width(str(hour)) for hour in self.hours) + 2 * pdf.c_margin
        )
        # Don't use unpacking (will fail if there is only 1 hour)
        # so first_hour and last_hour can be the same
        first_hour = self.hours[0]
        last_hour = self.hours[-1]
        for hour in self.hours:
            self.render_one_hour(hour, first_or_last=interval is not self.REAL_HOURS and hour in (first_hour, last_hour))

    def render_one_hour(self, hour: Hour, first_or_last=False):
        """Display one hour."""
        if first_or_last and settings.show_first_last is False:
            return
        pdf.y = self.y_for_hour(hour)
        border = "T"
        other_hours = set(h for h in self.hours if h != hour)
        if other_hours:
            nearest_hour = sorted(other_hours, key=lambda h: h.difference(hour))[0]
            if hour < nearest_hour and hour.difference(nearest_hour) < Hour(0, 20):
                pdf.y -= 6
                border = "B"

        real_hour = settings.real_hours.get(hour)

        # Display the hour in bold if there's the real hour
        emphasis = "B" if real_hour else ""
        with pdf.use_font_face(FontFace(emphasis=emphasis)):
            # Go under the cell to (optionally) draw the other cell
            pdf.cell(self.width, 6, str(hour), border, reduce=False, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)

        if real_hour:
            with pdf.use_font_face(FontFace(size_pt=10)):
                pdf.cell(self.width, 6, f"({real_hour})", reduce=False, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)

    def y_for_hour(self, hour: Hour) -> float:
        """Return the Y position on which we should display an hour."""
        assert self.start is not None, "Attempt to use y_for_hour on a timetable without hours"
        assert self.end is not None, "Attempt to use y_for_hour on a timetable without hours"

        if settings.wrap_hour:
            if hour == settings.wrap_hour:
                hour -= 0.5
            if hour > settings.wrap_hour:
                hour -= 1

        return (
            pdf.t_margin
            + settings.title_height
            + settings.day_height
            + timetable.eff_day_height * ((hour - self.start) / self.day_length)
        )

    def render_pause(self):
        """Render the two lines that represent the pause hours."""
        # Stop here if there are no hours
        if not self.start or not self.end:
            return

        # Create the pauses list
        pause_hours = []
        for day in self.timetable.days:
            pause_hours.extend(day.pauses)

        pause = HourRange.intersection(*pause_hours)
        if not pause:
            return

        # Draw a dashed line if we are in black and white mode, a red line otherwise
        settings = {"dash_pattern": {"dash": 2, "gap": 2}} if self.settings.black_white else {"draw_color": (255, 0, 0)}
        with pdf.local_context(**settings, line_width=0.5, stroke_cap_style=StrokeCapStyle.ROUND):
            for hour in (pause.start, pause.end):
                pdf.line(
                    pdf.l_margin,
                    self.y_for_hour(hour),
                    pdf.w - pdf.r_margin,
                    self.y_for_hour(hour),
                )
