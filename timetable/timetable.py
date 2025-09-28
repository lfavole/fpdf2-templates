from dataclasses import dataclass, field

from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace
from fpdf.fpdf import FPDF

from .ctxvars import cv_set, pdf, proxy, settings, timetable
from .days_manager import DaysManager
from .hours_manager import HoursManager
from .settings import Settings
from .utils import max_or_none, min_or_none


# @add_self_context_class(timetable)  # type: ignore
@proxy
@dataclass
class Timetable:
    """A timetable."""

    current = timetable
    needs_context = True

    title: str = "Timetable"
    days: DaysManager = field(default_factory=DaysManager)
    left_week: str = ""
    right_week: str = ""

    def __post_init__(self):
        self.hours = HoursManager(self)

    @property
    def start(self):
        return min_or_none(day.start for day in self.days)

    @property
    def end(self):
        return max_or_none(day.end for day in self.days)

    @classmethod
    def from_data(cls, data: str):
        """Create a timetable from data contained in a timetable file."""

        # Avoid circular imports
        from .tt_parser import TimetableParser

        return TimetableParser(data).timetable

    def move_lessons_if_needed(self):
        for day in self.days:
            day.move_lessons_if_needed()

    def render(self, _pdf: FPDF, _settings: Settings):
        """
        Display a timetable on a new page.
        """
        with cv_set(pdf, _pdf), cv_set(settings, _settings):
            for day in self.days:
                day.lessons = [lesson for lesson in day.lessons if lesson.is_displayed]

            pdf.add_page("L")
            self.render_title(self.title)

            pdf.set_font("", "", 12)
            self.hours.render()

            # Push the margin so epw (effective page width) is updated accordingly
            # and it's easier for the rest of the process
            pdf.l_margin += self.hours.width

            for i, day in enumerate(self.days):
                self.days.render(i, day)

            # Render the pause hours
            if settings.show_pause:
                self.hours.render_pause()

            # Restore the previous state
            pdf.l_margin -= self.hours.width

    @property
    def eff_day_height(self):
        """The effective height of a day (without the day name)."""
        return pdf.eph - settings.title_height - settings.day_height

    def render_title(self, title: str):
        """Render the title."""
        with pdf.use_font_face(FontFace(emphasis="B", size_pt=28)):
            pdf.x += self.hours.width
            pdf.y = 10
            if settings.title_shadow:
                with pdf.local_context(text_color=(143, 170, 220)):
                    pdf.x += 0.5
                    pdf.y += 0.5
                    pdf.cell(0, 15, title, align=Align.C, new_x=XPos.LEFT, new_y=YPos.TOP)
                    pdf.x -= 0.5
                    pdf.y -= 0.5

            with pdf.local_context(text_color=(68, 113, 196) if settings.title_shadow else None):
                pdf.cell(0, 15, title, align=Align.C, new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.x -= self.hours.width
