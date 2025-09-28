from fpdf.enums import Align, XPos, YPos

from .ctxvars import pdf, settings, timetable
from .day import Day


class DaysManager(list[Day]):
    """An object that manages a list of days."""

    needs_context = True

    def render(self, day_n: int, day: Day):
        """Render a day."""
        pdf.x = self.x_for_day(day_n)
        pdf.y = pdf.t_margin + settings.title_height

        # Write the heading cell (day of week)
        with pdf.local_context(font_style="B"):
            pdf.cell(self.day_width, 10, day.name, True, align=Align.C, new_x=XPos.LEFT, new_y=YPos.NEXT)

        # Draw a big rectangle that goes to bottom
        # so if the timetable finishes earlier, the column is still complete
        pdf.rect(pdf.x, pdf.y, self.day_width, timetable.eff_day_height)

        for lesson in day.lessons:
            lesson.render(day_n)

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
        return pdf.epw / len(timetable.days)

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
        return pdf.l_margin + self.day_width * day_n
