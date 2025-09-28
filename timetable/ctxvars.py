from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Generic, TypeVar, TYPE_CHECKING

from werkzeug.local import LocalProxy

if TYPE_CHECKING:
    from .patched_fpdf import PatchedFPDF
    from .settings import Settings
    from .timetable import Timetable


T = TypeVar("T")

# class LocalProxy(Generic[T]):
#     """A proxy to a `ContextVar` where you don't need to use `.get()` every time you want to access it."""

#     def __init__(self, name: str, *, default: T | None = None):
#         self._cv: ContextVar[T] = (
#             ContextVar(name)
#             if default is None
#             else ContextVar(name, default=default)
#         )

#     def __getattr__(self, name):
#         return getattr(self._cv.get(), name)

#     def __setattr__(self, name, value):
#         if name == "_cv":
#             super().__setattr__(name, value)
#             return
#         setattr(self._cv.get(), name, value)

#     def __delattr__(self, name):
#         if name == "_cv":
#             super().__delattr__(name)
#             return
#         delattr(self._cv.get(), name)

#     def __call__(self, *args, **kwargs):
#         return self._cv.get()(*args, **kwargs)


class Proxy(Generic[T]):
    """An object that keeps track of `ContextVar`s."""
    def __init__(self, cv: ContextVar[T], value: T, obj):
        self._cv = cv
        self._value = value
        self._obj = obj

    def __getattribute__(self, attr):
        if attr in ("_cv", "_value", "_obj"):
            return super().__getattribute__(attr)
        with cv_set(self._cv, self._value):
            ret = getattr(self._obj, attr)
        if hasattr(type(ret), "needs_context"):
            return Proxy(self._cv, self._value, ret)
        if callable(ret):
            @wraps(ret)
            def returnfunction(*args, **kwargs):
                with cv_set(self._cv, self._value):
                    return ret(*args, **kwargs)
            return returnfunction
        return ret

    def __call__(self, *args, **kwargs):
        with cv_set(self._cv, self._value):
            return self._obj(*args, **kwargs)

    def __iter__(self):
        with cv_set(self._cv, self._value):
            return iter(self._obj)

    def __len__(self):
        with cv_set(self._cv, self._value):
            return len(self._obj)


def proxy(cls):
    """
    Keep track of the current context when using attributes.

    This decorator adds a `current` attribute to the class.
    """
    old_getattribute = cls.__getattribute__

    def new_getattribute(self, attr):
        if attr == "current":
            return old_getattribute(self, attr)
        with cv_set(self.current._LocalProxy__wrapped, self):
            ret = old_getattribute(self, attr)
        if hasattr(type(ret), "needs_context"):
            return Proxy(self.current._LocalProxy__wrapped, self, ret)
        if callable(ret):
            @wraps(ret)
            def returnfunction(*args, **kwargs):
                with cv_set(self.current._LocalProxy__wrapped, self):
                    return ret(*args, **kwargs)
            return returnfunction
        return ret

    if "current" not in cls.__dict__:
        cls.current = LocalProxy(ContextVar(cls.__name__.lower()))

    cls.needs_context = True

    cls.__getattribute__ = new_getattribute

    return cls


@contextmanager
def cv_set(cv: ContextVar[T] | LocalProxy[T], value: T):
    if hasattr(cv, "__wrapped__"):
        cv = cv.__wrapped__
    token = cv.set(value)
    yield
    cv.reset(token)


def add_self_context(cv: LocalProxy[T]):
    def decorator(method):
        @wraps(method)
        def wrapper(self: T, *args, **kwargs):
            with cv_set(cv, self):
                return method(self, *args, **kwargs)

        return wrapper

    return decorator


def add_self_context_class(cv: LocalProxy[T]):
    def decorator(cls: type[T]):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, add_self_context(cv)(attr_value))

        return cls

    return decorator


pdf: "PatchedFPDF" = LocalProxy(ContextVar("pdf"))  # type: ignore
settings: "Settings" = LocalProxy(ContextVar("settings"))  # type: ignore
timetable: "Timetable" = LocalProxy(ContextVar("timetable"))  # type: ignore
