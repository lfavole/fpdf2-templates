from dataclasses import dataclass, field

from fpdf.drawing import DeviceRGB
from fpdf.enums import Align, RenderStyle, StrokeCapStyle, XPos, YPos
from fpdf.fonts import FontFace

from .ctxvars import pdf, settings, timetable
from .hour_range import HourRange
from .lesson_metrics import LessonMetrics
from .utils import Week, range_any


@dataclass
class Lesson(HourRange):
    """A lesson in a timetable."""

    name: str
    teacher: str
    room: int | str = ""
    color: str | DeviceRGB | None = None
    week: Week = Week.ALWAYS
    removed: bool = False
    tags: list[str] = field(default_factory=list)
    auto_moved: bool = False

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

    def __bool__(self):
        return bool(self.name) and super().__bool__()

    @property
    def styles(self):
        # The lesson name is in bold and the room is in italic
        return {
            "name": pdf.MARKDOWN_BOLD_MARKER,
            "room": pdf.MARKDOWN_ITALICS_MARKER,
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
            or settings.no_styles
            or any(marker in value for marker in pdf.all_markers)
            or not (marker_to_add := self.styles.get(key))
        ):
            return value

        return marker_to_add + value + marker_to_add

    @property
    def is_displayed(self):
        if settings.tags and all(tag not in settings.tags for tag in self.tags):
            return False
        if settings.no_tags and any(tag in settings.no_tags for tag in self.tags):
            return False
        return True

    def render(self, day_n: int):
        """Render a lesson."""
        if not self.is_displayed:
            raise RuntimeError("Attempt to display a non-displayed lesson")
        # Set the background if there is any
        if not self.color and settings.colors.get(self.name):
            self.color = settings.colors.get(self.name)

        if self.auto_moved:
            self.name += f" ({self.auto_moved[0].human_repr()} - {self.auto_moved[1].human_repr()})"

        if self.color and not settings.black_white:
            pdf.set_fill_color(self.color)  # type: ignore

        week = self.week
        metrics = LessonMetrics(
            pdf, timetable.left_week, timetable.right_week
        )
        metrics.x = (
            timetable.days.x_for_day(day_n)
            + {
                Week.ALWAYS: 0,
                Week.LEFT: 0,
                Week.RIGHT: 0.5,
            }[week]
            * timetable.days.day_width
        )
        metrics.start_y = timetable.hours.y_for_hour(self.start)
        metrics.end_y = timetable.hours.y_for_hour(self.end)
        pdf.x = metrics.x
        pdf.y = metrics.start_y

        metrics.day_width = timetable.days.day_width / (1 if week == Week.ALWAYS else 2)
        # Add all items to the list, otherwise it messes up the styles
        lines = {
            "name": self.name.strip(),
            "teacher": self.teacher.strip() if settings.show_teacher else "",
            "room": self.room.strip() if settings.show_room else "",  # type: ignore
        }
        week_shown = week != Week.ALWAYS and settings.show_weeks

        lines = {key: self._add_style(key, value) for key, value in lines.items() if value}

        if "room" in lines and not week_shown:
            metrics.calculate(week_shown, len(lines) - 1)  # without the room
            # If there's no space at the top and bottom, remove the room line
            # if not metrics.top_bottom_padding and "country" not in lines["name"]:
            teacher_and_room_width = pdf.get_string_width(f'{lines["teacher"]} ({lines["room"]})')
            if (
                not metrics.top_bottom_padding
                and (
                    teacher_and_room_width < metrics.day_width - 2 * pdf.c_margin
                    or teacher_and_room_width
                    < 1.5 * (metrics.day_width - 2 * pdf.c_margin)
                )
            ):
                lines["teacher"] += f' ({lines["room"]})'
                del lines["room"]

        metrics.calculate(week_shown, len(lines))

        x = pdf.x
        y = pdf.y
        # Draw a rectangle around the lesson
        # because lines are put as separate cells
        pdf.rect(
            x,
            y,
            metrics.day_width,
            metrics.height,
            RenderStyle.DF if self.color and not settings.black_white else RenderStyle.D,
        )

        # Leave some space at the top
        pdf.y += metrics.top_bottom_padding + metrics.top_padding

        for i, item in enumerate(lines.values()):
            if not item:
                continue

            width = metrics.day_width
            align = Align.C

            # the last cell of a week-dependent lesson
            if i == len(lines) - 1 and week_shown:
                text_width = pdf.get_string_width(item)
                if text_width > width - pdf.c_margin * 2:
                    # the text doesn't fit => only fit it on the left of the week
                    width -= metrics.week_width
                else:
                    side_space = (width - text_width) / 2
                    # if it overflows by x, remove x/2 to not make it overflow
                    overflow = metrics.week_width - side_space
                    if overflow > 0:
                        # width -= overflow * 2 - 2 * pdf.c_margin
                        width -= metrics.week_width
                        align = Align.R

            if "\n" in item:
                # Attempt to wrap only if there is a hard line break
                pdf.multi_cell(
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
                pdf.cell(
                    width, metrics.cell_height, item, align=align, new_x=XPos.LEFT, new_y=YPos.NEXT, markdown=True
                )

        # Leave some space at the bottom
        pdf.y += metrics.top_bottom_padding + metrics.bottom_padding

        # Display the week
        if week_shown:
            self.render_week(metrics, week)

        # Strike through if the lesson is removed
        if self.removed:
            self.striketrough(x, y, metrics.day_width, metrics.height)

    def render_week(self, metrics: LessonMetrics, week: Week):
        """Render the week at the pre-configured position."""
        with pdf.use_font_face(FontFace(size_pt=metrics.week_font_size)):
            a = pdf.x
            b = pdf.y
            pdf.x = metrics.x + metrics.day_width - metrics.week_width
            pdf.y = metrics.week_y_pos
            pdf.cell(
                metrics.week_width,
                metrics.week_height,
                {
                    Week.ALWAYS: "",
                    Week.LEFT: timetable.left_week,
                    Week.RIGHT: timetable.right_week,
                }[week],
                reduce=False,
                border=True,
                align=Align.C,
                new_x=XPos.RIGHT,
                new_y=YPos.TOP,
            )
            pdf.x = a
            pdf.y = b

    def striketrough(self, x, y, width, height):
        """Strike through a specified rectangular area, from top left to bottom right."""
        # Use butt style so the line doesn't overflow an already existing rectangle
        with pdf.local_context(stroke_cap_style=StrokeCapStyle.BUTT):
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

                pdf.line(x1, y1, x2, y2)
