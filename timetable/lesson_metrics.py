from dataclasses import dataclass

from fpdf import FPDF
from fpdf.fonts import FontFace


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
        return min(self.cell_height, self.week_font_size / self.pdf.k + 2 * self.week_margin)

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
