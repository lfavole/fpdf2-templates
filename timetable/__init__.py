import os
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, CharVPos, RenderStyle, StrokeCapStyle, XPos, YPos
from fpdf.fonts import FontFace
from fpdf.line_break import Fragment
from .tt_parser import TimetableParser
from .utils import CLI, Day, Hour, Lesson, Settings, Timetable, Week, app, range_any

left_week = ContextVar("left_week", default="")
right_week = ContextVar("right_week", default="")


class PatchedFPDF(FPDF):
    """
    A `FPDF` class that can draw better cells and add superscripts when needed.
    Recommended for use with timetables.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(False, 10)
        fonts_dir = Path("C:/Windows/Fonts") if sys.platform == "win32" else Path("/usr/share/fonts")
        self.add_font("Montserrat", "", fonts_dir / "Montserrat-Regular.ttf")
        self.add_font("Montserrat", "B", fonts_dir / "Montserrat-Bold.ttf")
        self.add_font("Montserrat", "I", fonts_dir / "Montserrat-Italic.ttf")
        self.add_font("Montserrat", "BI", fonts_dir / "Montserrat-BoldItalic.ttf")  # type: ignore
        self.set_font("Montserrat")

    def cell(
        self, w: float | None = None, h: float | None = None, txt: str = "", *args, **kwargs
    ):  # pylint: disable=W1113
        """Draw a cell."""
        if w == 0:
            w = self.w - self.r_margin - self.x
        font_size = None
        if (
            txt
            and txt not in (left_week.get(), right_week.get())
            and txt[-3:-2] != ":"
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

    def render(self, interval: Hour | float = 1):
        """Render the hours (at the left of the timetable) with the given interval."""
        if self.start_hour is None or self.end_hour is None:
            assert self.start_hour is None and self.end_hour is None, "Only one of the hours is None"
            return
        hours: list[Hour] = [
            *range_any(
                self.start_hour.ceil(interval),  # Start with the next hour (8:30 -> 9:00)...
                self.end_hour.floor(interval),  # ...and end with the previous hour (16:30 -> 16:00)
                interval,  # type: ignore
                include_end=True,
            )
        ]
        if not hours:
            # Stop here because getting the start and end hours will fail
            return
        # Don't use unpacking (will fail if there is only 1 hour)
        # so first_hour and last_hour can be the same
        first_hour = hours[0]
        last_hour = hours[-1]
        for hour in hours:
            self.render_one_hour(hour, first_or_last=hour in (first_hour, last_hour))

    def render_one_hour(self, hour: Hour, first_or_last=False):
        """Display one hour."""
        if first_or_last and self.renderer.settings.show_first_last is False:
            return
        self.renderer.pdf.y = self.y_for_hour(hour)
        # Don't move X and Y (X stays the same, Y is changed according to y_for_hour)
        self.renderer.pdf.cell(
            self.renderer.settings.hours_width, 6, str(hour), "T", align=Align.R, new_x=XPos.LEFT, new_y=YPos.TOP
        )

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
            + self.renderer.eff_day_height * ((hour - self.start_hour) / int(self.day_length))
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
        return self.pdf.c_margin / 2

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
        return self.week_font_size / self.pdf.k + 2 * self.week_margin

    @property
    def height(self):
        """
        The height of the cell.

        >>> LessonMetrics(FPDF(), "", "", start_y=10, end_y=30).height
        20
        """
        return self.end_y - self.start_y

    def calculate(self, week_shown: bool, items_n: int):
        """Calculate some values depending on the specified settings."""
        # Set the cell height depending on the number of items, limit to 7 mm
        self.cell_height = min(7, self.height / items_n)
        # Calculate the space to put at the top and bottom
        self.top_bottom_padding = max((self.height - items_n * self.cell_height) / 2, 0)

        # Rearrange space if we must write the week
        if week_shown:
            # If there is enough space to display the week at the bottom, display it there
            if self.top_bottom_padding + self.bottom_padding >= self.week_height * 0:
                self.week_y_pos = self.end_y - self.week_height  # Start writing above the week
                self.bottom_padding += self.week_height / 2.5
            else:
                # Otherwise display it at the top
                self.week_y_pos = self.start_y
                self.top_padding += self.week_height / 2.5

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

    def render_lesson(self, lesson: Lesson, day_n: int):
        """Render a lesson."""
        # Set the background if there is any
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
        items = [
            lesson.name.strip(),
            lesson.teacher.strip() if self.renderer.settings.show_teacher else "",
            lesson.room.strip() if self.renderer.settings.show_room else "",  # type: ignore
        ]

        items_n = sum(bool(item) for item in items)
        week_shown = week != Week.ALWAYS and self.renderer.settings.show_weeks
        metrics.calculate(week_shown, items_n)
        # if lesson_height < items_n * cell_height:
        #     cell_height = lesson_height / items_n
        # Calculate the cell height depending on paddings
        cell_height = (
            metrics.height - metrics.top_padding - 2 * metrics.top_bottom_padding - metrics.bottom_padding
        ) / items_n
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

        for i, item in enumerate(items):
            if not item:
                continue
            with self.renderer.pdf.use_font_face(FontFace(emphasis=("B", "", "I")[i])):
                if "\n" in item:
                    # Attempt to wrap only if there is a hard line break
                    self.renderer.pdf.multi_cell(
                        metrics.day_width,
                        cell_height,
                        item,
                        align=Align.C,
                        max_line_height=(cell_height / (item.count("\n") + 1)),
                        new_x=XPos.LEFT,
                        new_y=YPos.NEXT,
                    )
                else:
                    # Otherwise display everything on one line and reduce the font size
                    self.renderer.pdf.cell(
                        metrics.day_width, cell_height, item, align=Align.C, new_x=XPos.LEFT, new_y=YPos.NEXT
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
        token1 = left_week.set(self.renderer.timetable.left_week)
        token2 = right_week.set(self.renderer.timetable.right_week)
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
                True,
                align=Align.C,
                new_x=XPos.RIGHT,
                new_y=YPos.TOP,
            )
            self.renderer.pdf.x = a
            self.renderer.pdf.y = b
        left_week.reset(token1)
        right_week.reset(token2)

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
        self.hours.render()

        # Push the margin so epw (effective page width) is updated accordingly
        # and it's easier for the rest of the process
        self.pdf.l_margin += self.settings.hours_width

        for i, day in enumerate(self.timetable):
            self.days.render(i, day)

        # Restore the previous state
        self.pdf.l_margin -= self.settings.hours_width

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


base_path = Path(__file__).parent


def real_main(settings: CLI):
    pdf = PatchedFPDF("L")

    only_one_timetable = len(settings.timetable_paths) == 1

    for timetable in settings.timetable_paths:
        file = Path(timetable)
        result = TimetableParser(file.read_text("utf-8"))
        tt = result.timetable
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
