import argparse
import re
import warnings
from pprint import pp

from .utils import Day, Hour, Lesson, Settings, Timetable, Week

is_hr = re.compile(r"^---+$").match
get_lesson = re.compile(
    r"""(?x)
^
(?P<start> \d+ [:h] \d+ )
\s* - \s*
(?P<end> \d+ [:h] \d+ )
(?: \s+ (?P<name> (?:[^#].*?)? ) )?
(?: \s+ - \s+ (?P<teacher> (?:[^#].*?)? ) )?
(?: \s+ \( (?P<room>.*?) \) )?
(?: \s+ \( (?P<week>.*?) \) )?
(?: \s+ (?P<color>\#.*?) )?
(?P<removed> \s+ - \s+ Dispensé)?
$
"""
).match


class ParseError(ValueError):
    """An error that occured while parsing a timetable file."""

    def __init__(self, line: int, error: str):
        self.line = line
        self.error = error
        super().__init__(f"line {line}: {error}")


class ParseWarning(UserWarning, ValueError):
    """A lint warning that occured while parsing a timetable file."""

    def __init__(self, line: int, error: str):
        self.line = line
        self.error = error
        super().__init__(f"line {line}: {error}")


class TimetableParser:
    """Parse a timetable file. Return a list that corresponds to the timetable."""

    def __init__(self, data: str, lint=True):
        self.lint = lint

        self.timetable = Timetable()
        self.settings = Settings()

        self.in_config = False

        self.config: dict[str, str] = {}
        self.current_day_name: str | None = None
        self.current_day: Day | None = None

        # We use self.__dir__() because it gives the methods in the defined order (not in alphabetical order)
        parsers = [getattr(self, method) for method in self.__dir__() if method.startswith("parse_")]

        for i, line in enumerate(data.splitlines(), start=1):
            # Remove whitespace at the start and at the end of the line
            line = line.strip()
            for parser in parsers:
                if parser(i, line):
                    break
            else:
                raise ParseError(i, "No parser handled this line")

        if self.in_config:
            raise ValueError("Unexpected end of config, maybe you forgot to add --- at the end of the config?")

        self.timetable.title = self.config.get("title", self.timetable.title)
        self.timetable.left_week = self.config.get("left_week", "")
        self.timetable.right_week = self.config.get("right_week", "")

        # TODO add more settings: use the Settings class?
        self.settings.hours_width = int(self.config["hours_width"]) if "hours_width" in self.config else None
        self.settings.title_shadow = self.config.get("title_shadow", "").lower() == "true"

    def parse_empty_line_or_comment(self, _i: int, line: str) -> bool:
        """Skip empty lines and comments."""
        return not line or line[0] == "#"

    def parse_config_begin(self, i: int, line: str) -> bool:
        """If the first line is ---, it's the beginning of the config section."""
        if i != 1:
            return False
        if not is_hr(line):
            return False

        self.in_config = True
        if self.lint and len(line) > 3:
            warnings.warn(ParseWarning(i, "The length of the horizontal line before the config is longer than 3"))
        return True

    def parse_config_end(self, i: int, line: str) -> bool:
        """If we are in a config section and we encounter ---, it's the end of the config section."""
        if self.in_config and is_hr(line):
            if self.lint and not self.config:
                warnings.warn(ParseWarning(i, "Empty config"))
            self.in_config = False
            if self.lint and len(line) > 3:
                warnings.warn(ParseWarning(i, "The length of the horizontal line after the config is longer than 3"))
            return True
        return False

    def parse_config_option(self, i: int, line: str) -> bool:
        """If we are in a config section, try to parse the options."""
        if self.in_config:
            name, _, value = line.partition(":")
            if not value:
                raise ParseError(i, f"Invalid config option: {line!r}")
            self.config[name.strip()] = value.strip()
            return True
        return False

    def parse_lesson(self, i: int, line: str) -> bool:
        """If the line corresponds to a lesson, add it to the current day."""
        if match := get_lesson(line):
            if self.current_day is None:
                raise ParseError(i, "No current day, maybe you forgot to add --- after the day name?")

            week = Week.ALWAYS
            if match["week"]:
                if match["week"] == self.config.get("left_week"):
                    week = Week.LEFT
                elif match["week"] == self.config.get("right_week"):
                    week = Week.RIGHT
                else:
                    raise ParseError(i, f"Invalid week: {match['week']!r}")

            lesson = Lesson(
                start=Hour(match["start"]),
                end=Hour(match["end"]),
                name=match["name"] or "",
                teacher=match["teacher"] or "",
                room=match["room"] or "",
                color=match["color"] or self.config.get("color." + (match["name"] or "")),
                week=week,
                removed=bool(match["removed"]),
            )
            self.current_day.lessons.append(lesson)
            return True
        return False

    def parse_hr(self, i: int, line: str) -> bool:
        """If there is --- and a day name was already specified, create the day object."""
        if is_hr(line):
            if self.current_day_name is not None and self.current_day is None:
                self.current_day = Day(self.current_day_name)
                self.timetable.days.append(self.current_day)
                if self.lint and len(self.current_day_name) >= 3 and len(line) != len(self.current_day_name):
                    warnings.warn(
                        ParseWarning(
                            i,
                            "The length of the horizontal line doesn't match the length of the day "
                            f"(it should be {len(self.current_day_name)} but is {len(line)})",
                        )
                    )
                return True
            raise ParseError(i, f"Unexpected horizontal line at line {i}")
        return False

    def parse_day_name(self, i: int, line: str) -> bool:
        """In all the remaining cases, consider it's a day name."""
        if self.current_day_name is not None and self.current_day is None:
            raise ParseError(i, f"Unexpected day name at line {i}, maybe you meant to create a config section?")

        if self.lint and self.current_day_name is not None and not self.current_day and ":" in self.current_day_name:
            warnings.warn(ParseWarning(i, "Empty day"))

        self.current_day_name = line
        self.current_day = None
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("FILE", nargs="*", type=argparse.FileType("r"), help="file(s) to parse")
    args = parser.parse_args()
    for file in args.FILE:
        pp(TimetableParser(file.read()))
