"""Shared serializer/presentation helpers for celebrity payloads."""

from __future__ import annotations

from typing import Any, Mapping

from django.utils import timezone

from .presentation_dates import format_display_date, normalise_date


def calculate_age_years(birth_date: Any, end_date: Any = None) -> int | None:
    """Calculate age in full years, or ``None`` if unavailable/invalid."""
    birth = normalise_date(birth_date)
    if not birth:
        return None

    end = normalise_date(end_date) if end_date is not None else timezone.now().date()
    if not end:
        return None

    age = end.year - birth.year
    if (end.month, end.day) < (birth.month, birth.day):
        age -= 1

    return age if age >= 0 else None


def _get_value(source: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _iso_date(value: Any) -> str | None:
    parsed = normalise_date(value)
    return parsed.isoformat() if parsed else None


def build_celebrity_display_fields(
    birth_date: Any,
    death_date: Any,
    locale: str = "en",
) -> dict[str, Any]:
    """Build display-ready celebrity metadata shared by templates and JS."""
    birth = normalise_date(birth_date)
    death = normalise_date(death_date)
    is_deceased = death is not None

    birth_date_display = format_display_date(birth, locale=locale)
    death_date_display = format_display_date(death, locale=locale)

    age_value = calculate_age_years(birth, death if is_deceased else None)
    if age_value is None:
        age_display = None
    elif is_deceased:
        age_display = f"Died aged {age_value}"
    else:
        age_display = f"Age {age_value}"

    if birth_date_display and age_display:
        subtitle_display = f"Born on {birth_date_display} | {age_display}"
    elif birth_date_display:
        subtitle_display = f"Born on {birth_date_display}"
    else:
        subtitle_display = age_display

    return {
        "is_deceased": is_deceased,
        "birth_date_display": birth_date_display,
        "death_date_display": death_date_display,
        "age_value": age_value,
        "age_display": age_display,
        "subtitle_display": subtitle_display,
    }


def serialize_celebrity_payload(
    celebrity_data: Mapping[str, Any] | Any,
    locale: str = "en",
) -> dict[str, Any]:
    """Serialize celebrity fields with shared display metadata."""
    birth_date = _get_value(celebrity_data, "birth_date")
    death_date = _get_value(celebrity_data, "death_date")

    payload = {
        "id": _get_value(celebrity_data, "id"),
        "name": _get_value(celebrity_data, "name"),
        "bio": _get_value(celebrity_data, "bio"),
        "birth_date": _iso_date(birth_date),
        "death_date": _iso_date(death_date),
        "wikidata_id": _get_value(celebrity_data, "wikidata_id"),
        "image_url": _get_value(celebrity_data, "image_url") or "",
    }

    payload.update(build_celebrity_display_fields(birth_date, death_date, locale=locale))
    return payload
