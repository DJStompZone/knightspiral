"""Tiny Allure compatibility layer for local stripped-down test runs."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T", bound=Callable[..., Any])

try:
    import allure as allure
except ImportError:  # pragma: no cover - exercised only in minimal local environments.
    class _SeverityLevel:
        """String constants matching Allure severity values."""

        TRIVIAL = "trivial"
        MINOR = "minor"
        NORMAL = "normal"
        CRITICAL = "critical"
        BLOCKER = "blocker"

    class _AttachmentType:
        """Attachment MIME helpers matching the Allure public API shape."""

        TEXT = "text/plain"
        JSON = "application/json"
        PNG = "image/png"

    def _identity_decorator(*_args: Any, **_kwargs: Any) -> Callable[[T], T]:
        """Return a decorator that leaves the wrapped callable untouched."""
        return lambda wrapped: wrapped

    class _Dynamic:
        """No-op dynamic metadata writer."""

        def __getattr__(self, _name: str) -> Callable[..., None]:
            """Return a no-op metadata function."""
            return lambda *_args, **_kwargs: None

    class _Attach:
        """No-op attachment writer with an attach.file-compatible method."""

        def __call__(self, *_args: Any, **_kwargs: Any) -> None:
            """Ignore an in-memory attachment."""
            return None

        def file(self, *_args: Any, **_kwargs: Any) -> None:
            """Ignore a file attachment."""
            return None

    class _AllureShim:
        """No-op replacement for the subset of Allure used by the tests."""

        severity_level = _SeverityLevel
        attachment_type = _AttachmentType
        dynamic = _Dynamic()
        attach = _Attach()

        title = staticmethod(_identity_decorator)
        description = staticmethod(_identity_decorator)
        tag = staticmethod(_identity_decorator)
        severity = staticmethod(_identity_decorator)
        label = staticmethod(_identity_decorator)
        epic = staticmethod(_identity_decorator)
        feature = staticmethod(_identity_decorator)
        story = staticmethod(_identity_decorator)
        parent_suite = staticmethod(_identity_decorator)
        suite = staticmethod(_identity_decorator)
        sub_suite = staticmethod(_identity_decorator)

        @staticmethod
        @contextmanager
        def step(_title: str) -> Iterator[None]:
            """Provide a no-op context manager for Allure steps."""
            yield

    allure = _AllureShim()


def attach_text(name: str, body: str) -> None:
    """Attach text to the active Allure test when Allure is available."""
    allure.attach(body, name=name, attachment_type=allure.attachment_type.TEXT)


def attach_json(name: str, body: str) -> None:
    """Attach JSON text to the active Allure test when Allure is available."""
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)


def attach_png_file(path: Path, name: str) -> None:
    """Attach a PNG file to the active Allure test when Allure is available."""
    allure.attach.file(str(path), name=name, attachment_type=allure.attachment_type.PNG)
