import re

from fpdf import FPDF
from fpdf.enums import CharVPos
from fpdf.line_break import Fragment

from fonts import add_font


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
