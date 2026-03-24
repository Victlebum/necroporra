"""Date presentation helpers for localized UI output."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime
from typing import Any

from django.utils import formats, translation


def normalise_date(value: Any) -> date | None:
    """Normalize supported date-like values into a ``date`` instance."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        # Prefer full ISO parsing first, then a YYYY-MM-DD date part fallback.
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass

        date_part = raw.split("T", 1)[0]
        try:
            return date.fromisoformat(date_part)
        except ValueError:
            return None

    return None


def format_display_date(value: Any, locale: str = "en") -> str | None:
    """
    Format a date for display in the active UI language.

    Keeping date rendering in one helper makes localisation changes centralized.
    """
    date_value = normalise_date(value)
    if not date_value:
        return None

    language_context = translation.override(locale) if locale else nullcontext()
    with language_context:
        return formats.date_format(date_value, "j M Y", use_l10n=True)
