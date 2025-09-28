from dataclasses import dataclass, field

from .ctxvars import timetable
from .hour import Hour
from .hour_range import HourRange
from .lesson import Lesson
from .utils import max_or_none, min_or_none


@dataclass
class Day:
    """A day in a timetable."""

    needs_context = True  # because of timetable.end in move_lessons_if_needed

    name: str
    lessons: list[Lesson] = field(default_factory=list)

    @property
    def start(self):
        return min_or_none(lesson.start for lesson in self.lessons)

    @property
    def end(self):
        return max_or_none(lesson.end for lesson in self.lessons)

    @property
    def pauses(self):
        """
        Return an iterator on all the pauses on the current day:
        the specified pauses plus the implicit start and end pauses.

        >>> Day("Monday", [Lesson(Hour(8), Hour(11), "", ""), Lesson(Hour(13), Hour(11*7), "", "")])].pauses
        [HourRange(start=Hour(0, 0), end=Hour(8, 0)), HourRange(start=Hour(11, 0), end=Hour(13, 0)), HourRange(start=Hour(17, 0), end=Hour(23, 59))]
        """
        # If there are no lessons, stop here to avoid further problems
        if not self.lessons:
            return
        yield HourRange(Hour(0), self.start)
        prev_lesson: Lesson | None = None
        for lesson in self.lessons:
            # If the end hour of the previous lesson doesn't match the start hour of the current lesson,
            # then we need to add a pause
            if prev_lesson and lesson.start != prev_lesson.end:
                yield HourRange(prev_lesson.end, lesson.start)
            prev_lesson = lesson
        yield HourRange(self.end, Hour(-1, True))

    def move_lessons_if_needed(self):
        hour_slots: list[HourRange] = []
        for lesson in self.lessons:
            for hour_slot in hour_slots:
                if HourRange.intersection(hour_slot, lesson):
                    lesson.auto_moved = (lesson.start, lesson.end)
                    break

            if lesson.auto_moved:
                continue
            hour_slots.append(lesson)

        lessons_to_move = [lesson for lesson in self.lessons if lesson.auto_moved]
        if not lessons_to_move:
            return

        real_end_hour = max(lesson.end for lesson in self.lessons if not lesson.auto_moved)

        margin = Hour(1)
        max_length = Hour(1, 30)
        max_end_hour = timetable.end
        lesson_length = min((max_end_hour - real_end_hour) / len(lessons_to_move), max_length)

        start_hour = real_end_hour + margin
        for lesson in lessons_to_move:
            lesson.start = start_hour
            lesson.end = start_hour + lesson_length
            start_hour += lesson_length
