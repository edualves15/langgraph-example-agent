import calendar
from datetime import date, timedelta
from typing import Literal, Optional

from langchain_core.tools import tool


_WEEKDAY_NAMES_EN = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
    4: "Friday", 5: "Saturday", 6: "Sunday",
}

_WEEKDAY_NAMES_PT = {
    0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira", 3: "Quinta-feira",
    4: "Sexta-feira", 5: "Sábado", 6: "Domingo",
}

_MONTH_NAMES_EN = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

_MONTH_NAMES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}

_WEEKDAY_ALIASES: dict[str, int] = {
    "monday": 0, "mon": 0, "segunda": 0, "segunda-feira": 0,
    "tuesday": 1, "tue": 1, "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
    "wednesday": 2, "wed": 2, "quarta": 2, "quarta-feira": 2,
    "thursday": 3, "thu": 3, "quinta": 3, "quinta-feira": 3,
    "friday": 4, "fri": 4, "sexta": 4, "sexta-feira": 4,
    "saturday": 5, "sat": 5, "sábado": 5, "sabado": 5,
    "sunday": 6, "sun": 6, "domingo": 6,
}


def _parse_date(value: str) -> date:
    v = value.strip().lower()
    if v in ("today", "hoje"):
        return date.today()
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(
            f"Invalid date: '{value}'. Use ISO format YYYY-MM-DD, or the keyword 'today'."
        )


def _parse_weekday(value: str) -> int:
    key = value.strip().lower()
    if key not in _WEEKDAY_ALIASES:
        raise ValueError(
            f"Unknown weekday: '{value}'. Use English (monday … sunday), "
            f"Portuguese (segunda … domingo), or abbreviations (mon … sun)."
        )
    return _WEEKDAY_ALIASES[key]


def _iter_dates(start: date, end: date):
    """Itera, inclusive, de `start` a `end` (um `date` por dia)."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _quarter_start(d: date) -> date:
    return date(d.year, (_quarter(d) - 1) * 3 + 1, 1)


def _quarter_end(d: date) -> date:
    last_month = _quarter(d) * 3
    return date(d.year, last_month, calendar.monthrange(d.year, last_month)[1])


def _full_date_info(d: date) -> dict:
    yr, mo, day = d.year, d.month, d.day
    wd = d.weekday()
    days_in_month = calendar.monthrange(yr, mo)[1]
    return {
        "iso": d.isoformat(),
        "formatted_br": d.strftime("%d/%m/%Y"),
        "formatted_long_pt": f"{day} de {_MONTH_NAMES_PT[mo]} de {yr}",
        "formatted_long_en": f"{_MONTH_NAMES_EN[mo]} {day}, {yr}",
        "day": day,
        "month": mo,
        "year": yr,
        "month_name_en": _MONTH_NAMES_EN[mo],
        "month_name_pt": _MONTH_NAMES_PT[mo],
        "weekday_number": wd,
        "weekday_name_en": _WEEKDAY_NAMES_EN[wd],
        "weekday_name_pt": _WEEKDAY_NAMES_PT[wd],
        "is_weekend": wd >= 5,
        "iso_week_number": d.isocalendar()[1],
        "day_of_year": d.timetuple().tm_yday,
        "days_remaining_in_year": (date(yr, 12, 31) - d).days,
        "days_in_month": days_in_month,
        "days_remaining_in_month": days_in_month - day,
        "is_leap_year": calendar.isleap(yr),
        "quarter": _quarter(d),
        "quarter_start": _quarter_start(d).isoformat(),
        "quarter_end": _quarter_end(d).isoformat(),
        "month_start": date(yr, mo, 1).isoformat(),
        "month_end": date(yr, mo, days_in_month).isoformat(),
        "year_start": date(yr, 1, 1).isoformat(),
        "year_end": date(yr, 12, 31).isoformat(),
    }


@tool
def get_today_info() -> dict:
    """Return comprehensive information about today's date.

    Use when the user asks anything about the current date: the date itself, weekday,
    ISO week number, quarter, days left in the month/year, or whether it is a leap year.

    No input required.

    Returns a dict with the same fields as get_date_details: iso, formatted_br,
    formatted_long_pt/en, day/month/year, month/weekday names, is_weekend,
    iso_week_number, day_of_year, days_remaining_in_year, days_in_month,
    days_remaining_in_month, is_leap_year, quarter, and quarter/month/year boundaries.
    """
    return _full_date_info(date.today())


@tool
def get_date_details(date_str: str) -> dict:
    """Return comprehensive information about a specific date.

    Use when the user asks about a particular date: its weekday, ISO week, quarter, days
    in the month, whether the year is leap, or its quarter/year boundaries.

    Input:
    - date_str: a date in ISO format YYYY-MM-DD, or the keyword "today".

    Returns the same dict structure as get_today_info.
    """
    return _full_date_info(_parse_date(date_str))


@tool
def calculate_date_difference(start_date: str, end_date: str) -> dict:
    """Calculate the difference between two dates in multiple units at once.

    Use when the user asks how far apart two dates are (days/weeks/months/years), how
    many business days separate them, how long ago/until a date is, or someone's exact age.

    Input:
    - start_date: YYYY-MM-DD or "today".
    - end_date: YYYY-MM-DD or "today".

    Order does not matter — the span is always positive; `direction` says whether
    end_date is in the past/future/today relative to today.

    Returns a dict with: start, end (reordered so start <= end), total_days,
    complete_weeks, complete_months, complete_years, remaining_months_after_years,
    remaining_days_after_years_months (the exact years/months/days age breakdown),
    business_days (Mon–Fri), direction, is_same_date.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)

    total_days = (later - earlier).days

    years = later.year - earlier.year
    months = later.month - earlier.month
    days_r = later.day - earlier.day
    if days_r < 0:
        months -= 1
        anchor_month = (later.month - 2) % 12 + 1
        anchor_year = later.year if later.month > 1 else later.year - 1
        days_r += calendar.monthrange(anchor_year, anchor_month)[1]
    if months < 0:
        years -= 1
        months += 12

    today = date.today()
    direction = "today" if later == today else ("past" if later < today else "future")

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_days": total_days,
        "complete_weeks": total_days // 7,
        "complete_months": years * 12 + months,
        "complete_years": years,
        "remaining_months_after_years": months,
        "remaining_days_after_years_months": days_r,
        "business_days": sum(1 for d in _iter_dates(earlier, later) if d.weekday() < 5),
        "direction": direction,
        "is_same_date": start == end,
    }


@tool
def shift_date(
    base_date: str,
    amount: int,
    unit: Literal["days", "weeks", "months", "years"],
) -> dict:
    """Add or subtract a duration from a date to find a resulting date.

    Use when the user asks what date is N days/weeks/months/years from a date (or ago).

    Input:
    - base_date: YYYY-MM-DD or "today".
    - amount: integer. Positive → forward; negative → backward.
    - unit: one of "days", "weeks", "months", "years".

    Returns a dict with: base, result (ISO), result_details (full date info), and
    calendar_days_elapsed (absolute calendar days between base and result).
    """
    base = _parse_date(base_date)

    if unit == "days":
        result = base + timedelta(days=amount)
    elif unit == "weeks":
        result = base + timedelta(weeks=amount)
    elif unit == "months":
        total = base.month - 1 + amount
        new_year = base.year + total // 12
        new_month = total % 12 + 1
        max_day = calendar.monthrange(new_year, new_month)[1]
        result = date(new_year, new_month, min(base.day, max_day))
    elif unit == "years":
        new_year = base.year + amount
        max_day = calendar.monthrange(new_year, base.month)[1]
        result = date(new_year, base.month, min(base.day, max_day))
    else:
        raise ValueError(f"Invalid unit: '{unit}'. Use days, weeks, months, or years.")

    return {
        "base": base.isoformat(),
        "amount_applied": amount,
        "unit": unit,
        "direction": "forward" if amount >= 0 else "backward",
        "result": result.isoformat(),
        "result_details": _full_date_info(result),
        "calendar_days_elapsed": abs((result - base).days),
    }


def _parse_holidays(holidays: Optional[list[str]]) -> set[date]:
    parsed: set[date] = set()
    for h in holidays or []:
        try:
            parsed.add(_parse_date(h))
        except ValueError:
            pass
    return parsed


@tool
def count_business_days(
    start_date: str,
    end_date: str,
    holidays: Optional[list[str]] = None,
) -> dict:
    """Count business days (Mon–Fri) between two dates, optionally excluding holidays.

    Use when the user asks how many working days/weekdays fall in a range or until a deadline.

    Input:
    - start_date, end_date: YYYY-MM-DD or "today" (both inclusive).
    - holidays: optional list of ISO date strings (YYYY-MM-DD) to exclude.

    Returns a dict with: business_days, weekend_days, holidays_in_range, excluded_holidays.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)
    parsed_holidays = _parse_holidays(holidays)

    weekend_count = holiday_count = 0
    excluded: list[str] = []
    business = 0
    for d in _iter_dates(earlier, later):
        if d.weekday() >= 5:
            weekend_count += 1
        elif d in parsed_holidays:
            holiday_count += 1
            excluded.append(d.isoformat())
        else:
            business += 1

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_calendar_days": (later - earlier).days + 1,
        "business_days": business,
        "weekend_days": weekend_count,
        "holidays_in_range": holiday_count,
        "excluded_holidays": excluded,
    }


@tool
def add_business_days(
    start_date: str,
    business_days: int,
    holidays: Optional[list[str]] = None,
) -> dict:
    """Find the date that is exactly N business days after (or before) a date.

    Use when the user asks what date is N working days from a date (e.g. a deadline).

    Input:
    - start_date: YYYY-MM-DD or "today".
    - business_days: number of business days to advance (negative = backward).
    - holidays: optional list of ISO date strings to skip.

    Returns a dict with: result (ISO), result_details (full date info), and
    calendar_days_elapsed.
    """
    start = _parse_date(start_date)
    parsed_holidays = _parse_holidays(holidays)

    step = 1 if business_days >= 0 else -1
    remaining = abs(business_days)
    current = start
    while remaining > 0:
        current += timedelta(days=step)
        if current.weekday() < 5 and current not in parsed_holidays:
            remaining -= 1

    return {
        "start": start.isoformat(),
        "business_days_requested": business_days,
        "result": current.isoformat(),
        "result_details": _full_date_info(current),
        "calendar_days_elapsed": abs((current - start).days),
        "direction": "forward" if business_days >= 0 else "backward",
    }


@tool
def find_next_weekday(
    reference_date: str,
    weekday: str,
    direction: Literal["next", "previous"] = "next",
    include_reference: bool = False,
) -> dict:
    """Find the next or previous occurrence of a weekday relative to a date.

    Use when the user asks for the next/last occurrence of a weekday (e.g. next Monday).

    Input:
    - reference_date: YYYY-MM-DD or "today".
    - weekday: target day name (case-insensitive, EN or PT).
    - direction: "next" (default) or "previous".
    - include_reference: if True, the reference date itself counts when it already
      falls on the requested weekday.

    Returns a dict with: result (ISO), result_details (full date info), days_from_reference.
    """
    ref = _parse_date(reference_date)
    target = _parse_weekday(weekday)

    if direction == "next":
        delta = (target - ref.weekday()) % 7
        if delta == 0 and not include_reference:
            delta = 7
        result = ref + timedelta(days=delta)
    else:
        delta = (ref.weekday() - target) % 7
        if delta == 0 and not include_reference:
            delta = 7
        result = ref - timedelta(days=delta)

    return {
        "reference": ref.isoformat(),
        "weekday_requested": _WEEKDAY_NAMES_EN[target],
        "result": result.isoformat(),
        "result_details": _full_date_info(result),
        "days_from_reference": abs((result - ref).days),
        "direction": direction,
    }


@tool
def list_dates_in_range(
    start_date: str,
    end_date: str,
    filter_weekdays: Optional[list[str]] = None,
    only_business_days: bool = False,
) -> dict:
    """List all dates in a range, optionally filtered by weekday or business days.

    Use when the user asks to list dates (e.g. all Mondays in March) or how many times a
    weekday appears in a range.

    Input:
    - start_date, end_date: YYYY-MM-DD or "today" (both inclusive).
    - filter_weekdays: optional list of weekday names to include exclusively.
    - only_business_days: if True, return only Mon–Fri dates.

    Note: ranges over 730 days (2 years) are rejected.

    Returns a dict with: dates (list of ISO strings), count, filter_applied.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)

    total_calendar = (later - earlier).days + 1
    if total_calendar > 730:
        raise ValueError(
            f"Range of {total_calendar} days is too large. Use 730 days (2 years) or less."
        )

    if only_business_days:
        allowed: Optional[set[int]] = {0, 1, 2, 3, 4}
        filter_description = "business days (Mon–Fri)"
    elif filter_weekdays:
        allowed = {_parse_weekday(w) for w in filter_weekdays}
        names = ", ".join(_WEEKDAY_NAMES_EN[n] for n in sorted(allowed))
        filter_description = f"weekdays: {names}"
    else:
        allowed = None
        filter_description = "none (all dates)"

    dates = [
        d.isoformat() for d in _iter_dates(earlier, later)
        if allowed is None or d.weekday() in allowed
    ]

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_calendar_days": total_calendar,
        "dates": dates,
        "count": len(dates),
        "filter_applied": filter_description,
    }
