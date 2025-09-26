import os
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, CharVPos, MethodReturnValue, RenderStyle, StrokeCapStyle, XPos, YPos
from fpdf.fonts import FontFace
from fpdf.line_break import Fragment

from fonts import add_font
from .tt_parser import TimetableParser
from .utils import CLI, Day, Hour, Lesson, Pause, Pauses, PausesContainer, Settings, Timetable, Week, app, range_any


class PatchedFPDF(FPDF):
    """
    A `FPDF` class that can draw better cells and add superscripts when needed.
    Recommended for use with timetables.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(False, 10)
        add_font(self, "Montserrat")
        self.set_font("Montserrat")

        self.all_markers = set(
            getattr(self, attr)
            for attr in dir(self)
            if attr.startswith("MARKDOWN_") and attr.endswith("_MARKER")
        )

    def cell(
        self, w: float | None = None, h: float | None = None, txt: str = "", *args, reduce=True, **kwargs
    ):  # pylint: disable=W1113
        """Draw a cell."""
        if w == 0:
            w = self.w - self.r_margin - self.x
        font_size = None
        if (
            txt
            and reduce
            and w
            and (str_width := self.get_string_width(txt)) > (target_width := w - self.c_margin * 2)
        ):
            font_size = self.font_size_pt
            self.set_font_size(font_size * target_width / str_width)
        super().cell(w, h, txt, *args, **kwargs)
        if font_size is not None:
            self.set_font_size(font_size)

    def _preload_font_styles(self, text, markdown):
        """
        Apply superscripts to text.
        """
        frags: list[Fragment] = super()._preload_font_styles(text, markdown)  # type: ignore
        if len(frags) == 1 and not frags[0].characters:
            return frags

        ret = []
        for frag in frags:
            parts = re.split(r"((?<=[IVX]|\d)(?:e|er|ère|ème|nde)s?\b|(?<=M)me|(?<=T)a?le)", frag.string)
            for i, part in enumerate(parts):
                if not part:
                    continue
                new_frag = Fragment(part, frag.graphics_state.copy(), frag.k, frag.link)  # type: ignore
                if i % 2 == 1:  # group captured by the split regex
                    new_frag.graphics_state["char_vpos"] = CharVPos.SUP
                ret.append(new_frag)

        return ret


@dataclass
class HoursManager:
    """An object that manages the rendering of hours (at the left of the timetable)."""

    renderer: "TimetableRenderer"
    _hours_width: float | None = field(default=None, init=False)

    REAL_HOURS = object()

    def __post_init__(self):
        starts: list[Hour] = []
        ends: list[Hour] = []
        for day in self.renderer.timetable.days:
            for lesson in day:
                starts.append(lesson.start)
                ends.append(lesson.end)

        self.start_hour = min(starts) if starts else None
        self.end_hour = max(ends) if ends else None

    @property
    def day_length(self):
        """
        The day length (end hour - start hour).

        >>> hours = HoursManager(TimetableRenderer(Timetable()))
        >>> hours.start_hour
        >>> hours.end_hour
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
        >>> renderer.hours.start_hour
        Hour(8, 0)
        >>> renderer.hours.end_hour
        Hour(17, 0)
        >>> renderer.hours.day_length
        Hour(9, 0)
        """
        assert (
            self.start_hour is not None and self.end_hour is not None
        ), "Attempt to use day_length on a timetable without hours"
        return self.end_hour - self.start_hour

    @property
    def width(self):
        """The width of the hours column (at the left of the timetable)."""
        if self.renderer.settings.hours_width:
            return self.renderer.settings.hours_width
        assert self._hours_width, "hours_width should have been filled"
        return self._hours_width

    def render(self, interval: "Hour | float | type[HoursManager.REAL_HOURS] | None" = None):
        """Render the hours (at the left of the timetable) with the given interval."""
        if self.start_hour is None or self.end_hour is None:
            assert self.start_hour is None and self.end_hour is None, "Only one of the hours is None"
            return
        if interval is None:
            interval = 1
        if interval is self.REAL_HOURS:
            hours_set: set[Hour] = set()
            for day in self.renderer.timetable.days:
                for lesson in day:
                    hours_set.add(lesson.start)
                    hours_set.add(lesson.end)
            self.hours = sorted(hours_set)
        else:
            self.hours: list[Hour] = [
                *range_any(
                    self.start_hour.ceil(interval),  # Start with the next hour (8:30 -> 9:00)...
                    self.end_hour.floor(interval),  # ...and end with the previous hour (16:30 -> 16:00)
                    interval,  # type: ignore
                    include_end=True,
                )
            ]
        if not self.hours:
            # Stop here because getting the start and end hours will fail
            return
        self._hours_width = (
            max(self.renderer.pdf.get_string_width(str(hour)) for hour in self.hours) + 2 * self.renderer.pdf.c_margin
        )
        # Don't use unpacking (will fail if there is only 1 hour)
        # so first_hour and last_hour can be the same
        first_hour = self.hours[0]
        last_hour = self.hours[-1]
        for hour in self.hours:
            self.render_one_hour(hour, first_or_last=interval is not self.REAL_HOURS and hour in (first_hour, last_hour))

    def render_one_hour(self, hour: Hour, first_or_last=False):
        """Display one hour."""
        if first_or_last and self.renderer.settings.show_first_last is False:
            return
        self.renderer.pdf.y = self.y_for_hour(hour)
        border = "T"
        other_hours = set(h for h in self.hours if h != hour)
        if other_hours:
            nearest_hour = sorted(other_hours, key=lambda h: h.difference(hour))[0]
            if hour < nearest_hour and hour.difference(nearest_hour) < Hour(0, 20):
                self.renderer.pdf.y -= 6
                border = "B"

        real_hour = self.renderer.settings.real_hours.get(hour)

        # Display the hour in bold if there's the real hour
        emphasis = "B" if real_hour else ""
        with self.renderer.pdf.use_font_face(FontFace(emphasis=emphasis)):
            # Go under the cell to (optionally) draw the other cell
            self.renderer.pdf.cell(self.width, 6, str(hour), border, reduce=False, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)

        if real_hour:
            with self.renderer.pdf.use_font_face(FontFace(size_pt=10)):
                self.renderer.pdf.cell(self.width, 6, f"({real_hour})", reduce=False, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)

    def y_for_hour(self, hour: Hour) -> float:
        """Return the Y position on which we should display an hour."""
        assert self.start_hour is not None, "Attempt to use y_for_hour on a timetable without hours"
        assert self.end_hour is not None, "Attempt to use y_for_hour on a timetable without hours"

        if self.renderer.settings.wrap_hour:
            if hour == self.renderer.settings.wrap_hour:
                hour -= 0.5
            if hour > self.renderer.settings.wrap_hour:
                hour -= 1

        return (
            self.renderer.pdf.t_margin
            + self.renderer.settings.title_height
            + self.renderer.settings.day_height
            + self.renderer.eff_day_height * ((hour - self.start_hour) / self.day_length)
        )


@dataclass
class LessonMetrics:
    """Metrics about a lesson cell."""

    pdf: FPDF
    left_week: str
    right_week: str
    x: float = 0
    start_y: float = 0
    end_y: float = 0
    week_y_pos: float = 0
    day_width: float = 0
    cell_height: float = 0
    top_padding: float = 0
    bottom_padding: float = 0
    top_bottom_padding: float = 0

    week_font_size = 10

    @property
    def week_margin(self):
        """The margin in the week cells."""
        return self.pdf.c_margin / 2   # half of the normal cell margin!

    @property
    def week_width(self):
        """The width of a week label."""
        with self.pdf.use_font_face(FontFace(size_pt=self.week_font_size)):
            return (
                max(self.pdf.get_string_width(self.left_week), self.pdf.get_string_width(self.right_week))
                + 2 * self.week_margin
            )

    @property
    def week_height(self):
        """The height of a week label."""
        return min(self.cell_height,  self.week_font_size / self.pdf.k + 2 * self.week_margin)

    @property
    def height(self):
        """
        The height of the cell.

        >>> LessonMetrics(FPDF(), "", "", start_y=10, end_y=30).height
        20
        """
        return self.end_y - self.start_y

    @property
    def cell_height_other(self):
        """The height of the cell"""
        # if lesson_height < items_n * cell_height:
        #     cell_height = lesson_height / items_n
        # Calculate the cell height depending on paddings
        return (
            0
            if self.items_n == 0
            else (self.height - self.top_padding - 2 * self.top_bottom_padding - self.bottom_padding)
            / self.items_n
        )

    def calculate(self, week_shown: bool, items_n: int):
        """Calculate some values depending on the specified settings."""
        # Set the cell height depending on the number of items, limit to 7 mm
        self.cell_height = 7 if items_n == 0 else min(7, self.height / items_n)
        # Calculate the space to put at the top and bottom
        self.top_bottom_padding = max((self.height - items_n * self.cell_height) / 2, 0)

        # Rearrange space if we must write the week
        if week_shown:
            # If there is enough space to display the week at the bottom, display it there
            if self.top_bottom_padding + self.bottom_padding >= self.week_height * 0:
                self.week_y_pos = self.end_y - self.week_height  # Start writing above the week
                self.bottom_padding += self.week_height / (2.5 if items_n == 3 else 1.25)
            else:
                # Otherwise display it at the top
                self.week_y_pos = self.start_y
                self.top_padding += self.week_height / (2.5 if items_n == 3 else 1.25)

            # If some space is missing, add it
            # at the top or at the bottom (where the week is written)
            if self.top_bottom_padding < 0:
                if self.week_y_pos == self.start_y:
                    self.top_padding += -self.top_bottom_padding
                else:
                    self.bottom_padding += -self.top_bottom_padding
                self.top_bottom_padding = 0


@dataclass
class DaysManager:
    """An object that manages the rendering of days."""

    renderer: "TimetableRenderer"

    def render(self, day_n: int, day: Day):
        """Render a day."""
        x_day = self.x_for_day(day_n)
        self.renderer.pdf.x = x_day
        self.renderer.pdf.y = self.renderer.pdf.t_margin + self.renderer.settings.title_height

        # Write the heading cell (day of week)
        with self.renderer.pdf.local_context(font_style="B"):
            self.renderer.pdf.cell(self.day_width, 10, day.name, True, align=Align.C, new_x=XPos.LEFT, new_y=YPos.NEXT)

        # Draw a big rectangle that goes to bottom
        # so if the timetable finishes earlier, the column is still complete
        self.renderer.pdf.rect(self.renderer.pdf.x, self.renderer.pdf.y, self.day_width, self.renderer.eff_day_height)

        for lesson in day:
            self.render_lesson(lesson, day_n)

    @property
    def day_width(self):
        """
        The width of each day.

        >>> timetable = Timetable()
        >>> timetable.days.append(Day("..."))
        >>> timetable.days[0].lessons.extend([
        ...     Lesson(Hour(8), Hour(9), "", ""),
        ...     Lesson(Hour(16), Hour(17), "", ""),
        ... ])
        ...
        >>> renderer = TimetableRenderer(timetable)
        >>> renderer.pdf = FPDF()
        >>> renderer.days.day_width == renderer.pdf.epw
        True
        >>> timetable.days.append(timetable.days[0])
        >>> renderer.days.day_width == renderer.pdf.epw / 2
        True
        """
        return self.renderer.pdf.epw / len(self.renderer.timetable)

    def x_for_day(self, day_n: int):
        """
        Return the X position on which we should display a day.

        >>> timetable = Timetable()
        >>> timetable.days.append(Day("..."))
        >>> timetable.days[0].lessons.extend([
        ...     Lesson(Hour(8), Hour(9), "", ""),
        ...     Lesson(Hour(16), Hour(17), "", ""),
        ... ])
        ...
        >>> renderer = TimetableRenderer(timetable)
        >>> renderer.pdf = FPDF()
        >>> renderer.days.x_for_day(0) == renderer.pdf.l_margin
        True
        >>> timetable.days.append(timetable.days[0])
        >>> renderer.days.x_for_day(0) == renderer.pdf.l_margin
        True
        >>> renderer.days.x_for_day(1) == renderer.pdf.l_margin + renderer.pdf.epw / 2
        True
        """
        return self.renderer.pdf.l_margin + self.day_width * day_n


    @property
    def styles(self):
        # The lesson name is in bold and the room is in italic
        return {
            "name": self.renderer.pdf.MARKDOWN_BOLD_MARKER,
            "room": self.renderer.pdf.MARKDOWN_ITALICS_MARKER,
        }

    def _add_style(self, key, value):
        """
        Add Markdown styling to a lesson line.

        >>> timetable = Timetable()
        >>> timetable.days.append(Day("..."))
        >>> timetable.days[0].lessons.extend([
        ...     Lesson(Hour(8), Hour(9), "", ""),
        ...     Lesson(Hour(16), Hour(17), "", ""),
        ... ])
        ...
        >>> renderer = TimetableRenderer(timetable)
        >>> renderer.pdf = FPDF()
        >>> renderer._add_style("name", "test")
        "**test**"
        >>> renderer._add_style("teacher", "test")
        "test"
        >>> renderer._add_style("room", "test")
        "__test__"
        >>> renderer._add_style("name", "__test__")
        "__test__"
        """
        if (
            not value
            or self.renderer.settings.no_styles
            or any(marker in value for marker in self.renderer.pdf.all_markers)
            or not (marker_to_add := self.styles.get(key))
        ):
            return value

        return marker_to_add + value + marker_to_add

    def render_lesson(self, lesson: Lesson, day_n: int):
        """Render a lesson."""
        # Set the background if there is any
        if not lesson.color and self.renderer.settings.colors.get(lesson.name):
            lesson.color = self.renderer.settings.colors.get(lesson.name)

        if lesson.color and not self.renderer.settings.black_white:
            self.renderer.pdf.set_fill_color(lesson.color)  # type: ignore

        week = lesson.week
        metrics = LessonMetrics(
            self.renderer.pdf, self.renderer.timetable.left_week, self.renderer.timetable.right_week
        )
        metrics.x = (
            self.x_for_day(day_n)
            + {
                Week.ALWAYS: 0,
                Week.LEFT: 0,
                Week.RIGHT: 0.5,
            }[week]
            * self.day_width
        )
        metrics.start_y = self.renderer.hours.y_for_hour(lesson.start)
        metrics.end_y = self.renderer.hours.y_for_hour(lesson.end)
        self.renderer.pdf.x = metrics.x
        self.renderer.pdf.y = metrics.start_y

        metrics.day_width = self.day_width / (1 if week == Week.ALWAYS else 2)
        # Add all items to the list, otherwise it messes up the styles
        lines = {
            "name": lesson.name.strip(),
            "teacher": lesson.teacher.strip() if self.renderer.settings.show_teacher else "",
            "room": lesson.room.strip() if self.renderer.settings.show_room else "",  # type: ignore
        }
        week_shown = week != Week.ALWAYS and self.renderer.settings.show_weeks
        lines = {key: self._add_style(key, value) for key, value in lines.items() if value}

        if "room" in lines and not week_shown:
            metrics.calculate(week_shown, len(lines) - 1)  # without the room
            # If there's no space at the top and bottom, remove the room line
            if not metrics.top_bottom_padding and "country" not in lines["name"]:
                lines["teacher"] += f' ({lines["room"]})'
                del lines["room"]

        metrics.calculate(week_shown, len(lines))

        x = self.renderer.pdf.x
        y = self.renderer.pdf.y
        # Draw a rectangle around the lesson
        # because lines are put as separate cells
        self.renderer.pdf.rect(
            x,
            y,
            metrics.day_width,
            metrics.height,
            RenderStyle.DF if lesson.color and not self.renderer.settings.black_white else RenderStyle.D,
        )

        # Leave some space at the top
        self.renderer.pdf.y += metrics.top_bottom_padding + metrics.top_padding

        for i, (key, item) in enumerate(lines.items()):
            if not item:
                continue

            width = metrics.day_width
            align = Align.C

            # the last cell of a week-dependent lesson
            if i == len(lines) - 1 and week_shown:
                text_width = self.renderer.pdf.get_string_width(item)
                if text_width > width - self.renderer.pdf.c_margin * 2:
                    # the text doesn't fit => only fit it on the left of the week
                    width -= metrics.week_width
                else:
                    side_space = (width - text_width) / 2
                    # if it overflows by x, remove x/2 to not make it overflow
                    overflow = metrics.week_width - side_space
                    if overflow > 0:
                        # width -= overflow * 2 - 2 * self.renderer.pdf.c_margin
                        width -= metrics.week_width
                        align = Align.R

            if "\n" in item:
                # Attempt to wrap only if there is a hard line break
                self.renderer.pdf.multi_cell(
                    width,
                    metrics.cell_height,
                    item,
                    align=align,
                    max_line_height=(metrics.cell_height / (item.count("\n") + 1)),
                    new_x=XPos.LEFT,
                    new_y=YPos.NEXT,
                    markdown=True,
                )
            else:
                # Otherwise display everything on one line (because that reduces the font size if needed)
                self.renderer.pdf.cell(
                    width, metrics.cell_height, item, align=align, new_x=XPos.LEFT, new_y=YPos.NEXT, markdown=True
                )

        # Leave some space at the bottom
        self.renderer.pdf.y += metrics.top_bottom_padding + metrics.bottom_padding

        # Display the week
        if week_shown:
            self.render_week(metrics, week)

        # Strike through if the lesson is removed
        if lesson.removed:
            self.striketrough(x, y, metrics.day_width, metrics.height)

    def render_week(self, metrics: LessonMetrics, week: Week):
        """Render the week at the pre-configured position."""
        with self.renderer.pdf.use_font_face(FontFace(size_pt=metrics.week_font_size)):
            a = self.renderer.pdf.x
            b = self.renderer.pdf.y
            self.renderer.pdf.x = metrics.x + metrics.day_width - metrics.week_width
            self.renderer.pdf.y = metrics.week_y_pos
            self.renderer.pdf.cell(
                metrics.week_width,
                metrics.week_height,
                {
                    Week.ALWAYS: "",
                    Week.LEFT: self.renderer.timetable.left_week,
                    Week.RIGHT: self.renderer.timetable.right_week,
                }[week],
                reduce=False,
                border=True,
                align=Align.C,
                new_x=XPos.RIGHT,
                new_y=YPos.TOP,
            )
            self.renderer.pdf.x = a
            self.renderer.pdf.y = b

    def striketrough(self, x, y, width, height):
        """Strike through a specified rectangular area, from top left to bottom right."""
        # Use butt style so the line doesn't overflow an already existing rectangle
        with self.renderer.pdf.local_context(stroke_cap_style=StrokeCapStyle.BUTT):
            step = 5  # mm
            position = step
            maximum = height + width
            # 15 20 25 30 ...
            # 10
            #  5
            #  0

            # Don't start at 0 because the line immediatly stops
            for position in range_any(step, maximum, step):
                # Limit the starting point to the cell: don't overflow on left or top
                # # From 15 on, count the position - 15
                x1 = (x + position - height) if position >= height else x
                # Before 15, start from the bottom and move `position` upwards
                y1 = (y + height - position) if position <= height else y

                # End position of the line
                x2 = x1 + height
                y2 = y1 + height

                # Limit the line to the bottom of the cell
                if y2 > y + height:
                    # ┌────────┐
                    # │        │
                    # │a       │
                    # └─*──────┘ ← y + height \
                    #    *                    | diff
                    #      b     ← y2         /
                    # Calculate the difference and remove it to x and y (to keep the line in the good direction)
                    diff = y2 - (y + height)
                    y2 -= diff
                    x2 -= diff

                # Limit the line to the right of the cell
                if x2 > x + width:
                    # ┌────────┐
                    # │       a│
                    # │        *
                    # └────────┘*
                    #            b
                    # x+width ↑  ↑ x2
                    #         \__/ diff
                    # Calculate the difference and remove it to x and y (to keep the line in the good direction)
                    diff = x2 - (x + width)
                    x2 -= diff
                    y2 -= diff

                self.renderer.pdf.line(x1, y1, x2, y2)


@dataclass
class TimetableRenderer:
    """An object that can render a timetable inside of a PDF."""

    timetable: Timetable
    settings: Settings | CLI = field(default_factory=Settings)
    pdf: FPDF = field(init=False)

    def __post_init__(self):
        self.hours = HoursManager(self)
        self.days = DaysManager(self)

    def render(self, pdf: FPDF):
        """
        Display a timetable on a new page.
        """
        self.pdf = pdf
        self.pdf.add_page("L")
        self.render_title(self.timetable.title)

        self.pdf.set_font("", "", 12)
        self.hours.render(HoursManager.REAL_HOURS if self.settings.render_real_hours else None)

        # Push the margin so epw (effective page width) is updated accordingly
        # and it's easier for the rest of the process
        self.pdf.l_margin += self.hours.width

        for i, day in enumerate(self.timetable):
            self.days.render(i, day)

        # Render the pause hours
        if self.settings.show_pause:
            self.render_pause()

        # Restore the previous state
        self.pdf.l_margin -= self.hours.width

    @property
    def eff_day_height(self):
        """The effective height of a day (without the day name)."""
        return self.pdf.eph - self.settings.title_height - self.settings.day_height

    def render_title(self, title: str):
        """Render the title."""
        with self.pdf.use_font_face(FontFace(emphasis="B", size_pt=28)):
            self.pdf.x = 20
            self.pdf.y = 10
            if self.settings.title_shadow:
                with self.pdf.local_context(text_color=(143, 170, 220)):
                    self.pdf.x += 0.5
                    self.pdf.y += 0.5
                    self.pdf.cell(0, 15, title, align=Align.C, new_x=XPos.LEFT, new_y=YPos.TOP)
                    self.pdf.x -= 0.5
                    self.pdf.y -= 0.5

            with self.pdf.local_context(text_color=(68, 113, 196) if self.settings.title_shadow else None):
                self.pdf.cell(0, 15, title, align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def render_pause(self):
        """Render the two lines that represent the pause hours."""
        # Stop here if there are no hours
        if not self.hours.start_hour or not self.hours.end_hour:
            return

        # Create the pauses container
        pause_hours = PausesContainer(self.hours.start_hour, self.hours.end_hour)
        for day in self.timetable.days:
            # If there are no lessons, stop here to avoid further problems
            if not day.lessons:
                continue
            # Create the pauses list for each day and add it
            pauses_for_today = Pauses(day.lessons[0].start, day.lessons[-1].end)
            pause_hours.days.append(pauses_for_today)

            prev_lesson: Lesson | None = None
            for lesson in day:
                # If the end hour of the previous lesson doesn't match the start hour of the current lesson,
                # then we need to add a pause
                if prev_lesson and lesson.start != prev_lesson.end:
                    pauses_for_today.pauses.append(Pause(prev_lesson.end, lesson.start))
                prev_lesson = lesson

        pause = pause_hours.intersection()
        if not pause:
            return

        # Draw a dashed line if we are in black and white mode, a red line otherwise
        settings = {"dash_pattern": {"dash": 2, "gap": 2}} if self.settings.black_white else {"draw_color": (255, 0, 0)}
        with self.pdf.local_context(**settings, line_width=0.5, stroke_cap_style=StrokeCapStyle.ROUND):
            for hour in (pause.start, pause.end):
                self.pdf.line(
                    self.pdf.l_margin,
                    self.hours.y_for_hour(hour),
                    self.pdf.w - self.pdf.r_margin,
                    self.hours.y_for_hour(hour),
                )


base_path = Path(__file__).parent


def real_main(settings: CLI):
    pdf = PatchedFPDF("L")

    only_one_timetable = len(settings.timetable_paths) == 1

    for timetable in settings.timetable_paths:
        file = Path(timetable)
        result = TimetableParser(file.read_text("utf-8"))
        tt = result.timetable
        tt.move_lessons_if_needed()
        TimetableRenderer(tt, Settings.merge(result.settings, settings)).render(pdf)
        if only_one_timetable:
            pdf.set_title(tt.title)

    file = settings.output
    if isinstance(file, str):
        file = file % {"timetables": "_".join(re.split(r"[\\/]", path)[-1] for path in settings.timetable_paths)}

    pdf.output(str(file))
    if settings.open:
        os.startfile(file)  # type: ignore


def main():
    app()


if __name__ == "__main__":
    main()
