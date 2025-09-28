import os
import re
from pathlib import Path

from .patched_fpdf import PatchedFPDF
from .settings import Settings, CLI, app
from .tt_parser import TimetableParser


base_path = Path(__file__).parent


def real_main(settings: CLI):
    pdf = PatchedFPDF("L")

    only_one_timetable = len(settings.timetable_paths) == 1

    for timetable in settings.timetable_paths:
        file = Path(timetable)
        result = TimetableParser(file.read_text("utf-8"))
        tt = result.timetable
        tt.move_lessons_if_needed()
        tt.render(pdf, Settings.merge(result.settings, settings))
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
