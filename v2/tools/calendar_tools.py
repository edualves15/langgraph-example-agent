import calendar
from datetime import date, timedelta
from typing import Literal, Optional

from langchain_core.tools import tool


# Tool design best practices are used here to maximize LLM understanding:
# - clear tool name
# - precise type hints
# - capability-focused docstring
# - explicit usage rules
# - concrete examples
# - deterministic, dependency-free implementation


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

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

# Accepts English, Portuguese, and common abbreviations
_WEEKDAY_ALIASES: dict[str, int] = {
    "monday": 0, "mon": 0, "segunda": 0, "segunda-feira": 0,
    "tuesday": 1, "tue": 1, "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
    "wednesday": 2, "wed": 2, "quarta": 2, "quarta-feira": 2,
    "thursday": 3, "thu": 3, "quinta": 3, "quinta-feira": 3,
    "friday": 4, "fri": 4, "sexta": 4, "sexta-feira": 4,
    "saturday": 5, "sat": 5, "sábado": 5, "sabado": 5,
    "sunday": 6, "sun": 6, "domingo": 6,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> date:
    """
    Parse a date string.

    Accepts:
    - "today" or "hoje" → current date
    - "YYYY-MM-DD"      → ISO 8601 format
    """
    v = value.strip().lower()
    if v in ("today", "hoje"):
        return date.today()
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(
            f"Invalid date: '{value}'. "
            f"Use ISO format YYYY-MM-DD, or the keyword 'today'."
        )


def _parse_weekday(value: str) -> int:
    """Return 0–6 (Mon–Sun) from a weekday name string. Raises ValueError on unknown input."""
    key = value.strip().lower()
    if key not in _WEEKDAY_ALIASES:
        raise ValueError(
            f"Unknown weekday: '{value}'. "
            f"Use English (monday … sunday) or Portuguese (segunda … domingo), "
            f"or abbreviations (mon, tue, wed, thu, fri, sat, sun)."
        )
    return _WEEKDAY_ALIASES[key]


def _quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _quarter_start(d: date) -> date:
    first_month = (_quarter(d) - 1) * 3 + 1
    return date(d.year, first_month, 1)


def _quarter_end(d: date) -> date:
    last_month = _quarter(d) * 3
    return date(d.year, last_month, calendar.monthrange(d.year, last_month)[1])


def _count_business_days_range(
    start: date, end: date, holidays: set[date]
) -> int:
    """Count Mon–Fri days between start and end (inclusive), excluding holidays."""
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            count += 1
        current += timedelta(days=1)
    return count


def _full_date_info(d: date) -> dict:
    """Return a comprehensive descriptor dict for a given date."""
    yr, mo, day = d.year, d.month, d.day
    weekday_num = d.weekday()
    days_in_month = calendar.monthrange(yr, mo)[1]
    is_leap = calendar.isleap(yr)
    day_of_year = d.timetuple().tm_yday
    days_in_year = 366 if is_leap else 365
    iso_year, iso_week, iso_weekday = d.isocalendar()
    q = _quarter(d)
    q_start = _quarter_start(d)
    q_end = _quarter_end(d)
    month_start = date(yr, mo, 1)
    month_end = date(yr, mo, days_in_month)
    year_start = date(yr, 1, 1)
    year_end = date(yr, 12, 31)

    return {
        # Formatted representations
        "iso": d.isoformat(),
        "formatted_br": d.strftime("%d/%m/%Y"),
        "formatted_us": d.strftime("%m/%d/%Y"),
        "formatted_long_pt": f"{day} de {_MONTH_NAMES_PT[mo]} de {yr}",
        "formatted_long_en": f"{_MONTH_NAMES_EN[mo]} {day}, {yr}",
        # Date components
        "day": day,
        "month": mo,
        "year": yr,
        "month_name_en": _MONTH_NAMES_EN[mo],
        "month_name_pt": _MONTH_NAMES_PT[mo],
        # Weekday
        "weekday_number": weekday_num,          # 0 = Monday, 6 = Sunday
        "weekday_name_en": _WEEKDAY_NAMES_EN[weekday_num],
        "weekday_name_pt": _WEEKDAY_NAMES_PT[weekday_num],
        "is_weekday": weekday_num < 5,
        "is_weekend": weekday_num >= 5,
        # ISO week
        "iso_week_number": iso_week,
        "iso_week_year": iso_year,
        # Position within year/month
        "day_of_year": day_of_year,
        "days_in_year": days_in_year,
        "days_elapsed_in_year": day_of_year,
        "days_remaining_in_year": (year_end - d).days,
        "days_in_month": days_in_month,
        "days_remaining_in_month": days_in_month - day,
        "is_last_day_of_month": day == days_in_month,
        "is_first_day_of_month": day == 1,
        # Year traits
        "is_leap_year": is_leap,
        # Quarter
        "quarter": q,
        "quarter_label": f"Q{q} {yr}",
        "quarter_start": q_start.isoformat(),
        "quarter_end": q_end.isoformat(),
        "days_remaining_in_quarter": (q_end - d).days,
        # Boundary dates
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "year_start": year_start.isoformat(),
        "year_end": year_end.isoformat(),
        # Unix
        "unix_timestamp": int((d - date(1970, 1, 1)).total_seconds()),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_today_info() -> dict:
    """
    Return comprehensive information about today's date.

    Use this tool whenever the user asks about the current date, such as:
    - What is today's date?
    - What day of the week is it today?
    - What week number are we in?
    - What quarter is it?
    - How many days are left in this month / year?
    - Is this year a leap year?
    - When does the current quarter or year end?

    No input required.

    Returns a dict with:
    - iso: "YYYY-MM-DD"
    - formatted_br: "DD/MM/YYYY"
    - formatted_us: "MM/DD/YYYY"
    - formatted_long_pt: "15 de março de 2025"
    - formatted_long_en: "March 15, 2025"
    - day, month, year: integer components
    - month_name_en, month_name_pt: month name
    - weekday_number: 0 (Monday) to 6 (Sunday)
    - weekday_name_en, weekday_name_pt: weekday name
    - is_weekday, is_weekend: booleans
    - iso_week_number: ISO 8601 week (1–53)
    - day_of_year: ordinal day within the year (1–366)
    - days_remaining_in_year: calendar days until December 31
    - days_in_month: total days in the current month
    - days_remaining_in_month: days until end of month
    - is_leap_year: boolean
    - quarter: 1–4
    - quarter_label: "Q2 2025"
    - quarter_start, quarter_end: ISO boundary dates
    - days_remaining_in_quarter: days until end of quarter
    - month_start, month_end, year_start, year_end: ISO boundary dates
    - unix_timestamp: seconds since Unix epoch
    """
    return _full_date_info(date.today())


@tool
def get_date_details(date_str: str) -> dict:
    """
    Return comprehensive information about any specific date.

    Use this tool to look up details about a particular date, such as:
    - What day of the week was/is a specific date?
    - What week number does a date fall in?
    - What quarter is a date in?
    - How many days are in the month of that date?
    - When does that date's quarter / year start and end?
    - Is the year of that date a leap year?
    - Is the date a weekday or weekend?
    - What is the ISO week number of a date?

    Input:
    - date_str: a date in ISO format YYYY-MM-DD, or the keyword "today".

    Good inputs:
    - "2025-03-15"
    - "2000-02-29"
    - "today"

    Returns the same dict structure as get_today_info.
    """
    return _full_date_info(_parse_date(date_str))


@tool
def calculate_date_difference(start_date: str, end_date: str) -> dict:
    """
    Calculate the difference between two dates in multiple units simultaneously.

    Use this tool whenever the user asks:
    - How many days between X and Y?
    - How many weeks apart are two dates?
    - How many months / years is the gap between X and Y?
    - How many business days between X and Y?
    - How long ago was date X?
    - How long until date Y?
    - What is the exact age (years, months, days) of something since date X?
    - How old is a person born on date X?

    Input:
    - start_date: YYYY-MM-DD or "today"
    - end_date: YYYY-MM-DD or "today"

    Order does not matter — the result is always expressed as a positive span.
    The "direction" field tells you whether end_date is in the past or future
    relative to today.

    Good inputs:
    - start_date="1990-06-15", end_date="today"   → age calculation
    - start_date="2025-01-01", end_date="2025-12-31"  → days in a year
    - start_date="today", end_date="2025-08-10"   → days until a deadline

    Returns a dict with:
    - start, end: ISO dates (reordered so start <= end)
    - total_days: exact calendar days (exclusive of both boundaries)
    - total_days_inclusive: total_days + 1 (both boundaries counted)
    - complete_weeks: whole 7-day weeks in the span
    - remaining_days_after_weeks: leftover days (0–6)
    - complete_months: whole calendar months in the span
    - complete_years: whole calendar years in the span
    - remaining_months_after_years: leftover months after extracting years
    - remaining_days_after_years_months: leftover days after extracting years and months
    - approximate_months: float approximation (total_days / 30.44)
    - business_days: Mon–Fri day count (no holiday adjustment)
    - direction: "past" | "future" | "today" — end's relation to today
    - is_same_date: true if start == end
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)

    total_days = (later - earlier).days
    complete_weeks, remaining_days_after_weeks = divmod(total_days, 7)

    # Calendar-accurate years / months / days decomposition
    years = later.year - earlier.year
    months = later.month - earlier.month
    days_r = later.day - earlier.day

    if days_r < 0:
        months -= 1
        prev_month = earlier.month + months  # month just before 'later' in the span
        # Move back to get the right anchor
        anchor_year = later.year if later.month > 1 else later.year - 1
        anchor_month = (later.month - 2) % 12 + 1
        days_r += calendar.monthrange(anchor_year, anchor_month)[1]

    if months < 0:
        years -= 1
        months += 12

    complete_months_total = years * 12 + months
    approximate_months = round(total_days / 30.4375, 2)

    bdays = _count_business_days_range(earlier, later, set())

    today = date.today()
    if later < today:
        direction = "past"
    elif later == today:
        direction = "today"
    else:
        direction = "future"

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_days": total_days,
        "total_days_inclusive": total_days + 1,
        "complete_weeks": complete_weeks,
        "remaining_days_after_weeks": remaining_days_after_weeks,
        "complete_months": complete_months_total,
        "complete_years": years,
        "remaining_months_after_years": months,
        "remaining_days_after_years_months": days_r,
        "approximate_months": approximate_months,
        "business_days": bdays,
        "direction": direction,
        "is_same_date": start == end,
    }


@tool
def shift_date(
    base_date: str,
    amount: int,
    unit: Literal["days", "weeks", "months", "years"],
) -> dict:
    """
    Add or subtract a duration from a date to find a resulting date.

    Use this tool whenever the user asks:
    - What date is N days / weeks / months / years from X?
    - What was the date N days / months ago?
    - When will it be N months from today?
    - What is the deadline if I add N weeks to a date?
    - What is the same day next year / last year?
    - What date is N years before X?

    Input:
    - base_date: the starting date in YYYY-MM-DD format, or "today".
    - amount: integer. Positive → move forward. Negative → move backward.
    - unit: one of "days", "weeks", "months", "years".

    Month/year arithmetic clamps to the last valid day when needed
    (e.g., January 31 + 1 month → February 28 or 29).

    Good inputs:
    - base_date="today", amount=30, unit="days"      → 30 days from today
    - base_date="2025-01-31", amount=1, unit="months" → 2025-02-28
    - base_date="today", amount=-6, unit="months"     → 6 months ago
    - base_date="2024-02-29", amount=1, unit="years"  → 2025-02-28

    Returns a dict with:
    - base: original date ISO
    - amount_applied: the amount used (may be negative)
    - unit: the unit used
    - direction: "forward" or "backward"
    - result: resulting date ISO
    - result_details: full date info dict for the result (same as get_date_details)
    - calendar_days_elapsed: absolute calendar days between base and result
    """
    base = _parse_date(base_date)

    if unit == "days":
        result = base + timedelta(days=amount)

    elif unit == "weeks":
        result = base + timedelta(weeks=amount)

    elif unit == "months":
        new_month = base.month + amount
        years_delta = (new_month - 1) // 12
        new_month = (new_month - 1) % 12 + 1
        new_year = base.year + years_delta
        max_day = calendar.monthrange(new_year, new_month)[1]
        result = date(new_year, new_month, min(base.day, max_day))

    elif unit == "years":
        new_year = base.year + amount
        max_day = calendar.monthrange(new_year, base.month)[1]
        result = date(new_year, base.month, min(base.day, max_day))

    else:
        raise ValueError(
            f"Invalid unit: '{unit}'. Must be 'days', 'weeks', 'months', or 'years'."
        )

    return {
        "base": base.isoformat(),
        "amount_applied": amount,
        "unit": unit,
        "direction": "forward" if amount >= 0 else "backward",
        "result": result.isoformat(),
        "result_details": _full_date_info(result),
        "calendar_days_elapsed": abs((result - base).days),
    }


@tool
def count_business_days(
    start_date: str,
    end_date: str,
    holidays: Optional[list[str]] = None,
) -> dict:
    """
    Count business days (Monday–Friday) between two dates, optionally excluding holidays.

    Use this tool when the user asks:
    - How many working days are there between X and Y?
    - How many business days until a deadline?
    - How many weekdays are there in this month?
    - Count work days between two dates, skipping holidays.

    Input:
    - start_date: YYYY-MM-DD or "today" (inclusive).
    - end_date: YYYY-MM-DD or "today" (inclusive).
    - holidays: optional list of ISO date strings (YYYY-MM-DD) to treat as non-working days.
      Example: ["2025-01-01", "2025-04-18"]

    Order does not matter.

    Good inputs:
    - start_date="2025-01-01", end_date="2025-01-31"
    - start_date="today", end_date="2025-12-31", holidays=["2025-12-25"]

    Returns a dict with:
    - start, end: ISO boundary dates (reordered so start <= end)
    - total_calendar_days: total days inclusive (end - start + 1)
    - business_days: Mon–Fri days, excluding provided holidays
    - weekend_days: Saturday + Sunday count in the span
    - holidays_in_range: how many provided holidays fell within the range
    - excluded_holidays: list of holiday ISO dates that were inside the range
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)

    parsed_holidays: set[date] = set()
    if holidays:
        for h in holidays:
            try:
                parsed_holidays.add(_parse_date(h))
            except ValueError:
                pass  # skip invalid entries silently

    total_calendar = (later - earlier).days + 1
    weekend_count = 0
    holiday_count = 0
    excluded: list[str] = []

    current = earlier
    while current <= later:
        if current.weekday() >= 5:
            weekend_count += 1
        elif current in parsed_holidays:
            holiday_count += 1
            excluded.append(current.isoformat())
        current += timedelta(days=1)

    bdays = total_calendar - weekend_count - holiday_count

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_calendar_days": total_calendar,
        "business_days": bdays,
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
    """
    Find the date that is exactly N business days after (or before) a starting date.

    Use this tool when the user asks:
    - What date is 10 business days from today?
    - When is the delivery deadline if it's N working days from date X?
    - What date falls N weekdays after a given date?
    - What was the date N business days ago?

    This is different from count_business_days, which counts days in a range.
    This tool finds the target date given a count.

    Input:
    - start_date: YYYY-MM-DD or "today".
    - business_days: number of business days to advance. Negative = go backward.
    - holidays: optional list of ISO date strings to skip (YYYY-MM-DD).

    Good inputs:
    - start_date="today", business_days=10
    - start_date="2025-06-01", business_days=-5, holidays=["2025-05-29"]

    Returns a dict with:
    - start: the starting ISO date
    - business_days_requested: the N provided
    - result: the resulting ISO date
    - result_details: full date info for the result
    - calendar_days_elapsed: absolute calendar days between start and result
    - direction: "forward" or "backward"
    """
    start = _parse_date(start_date)

    parsed_holidays: set[date] = set()
    if holidays:
        for h in holidays:
            try:
                parsed_holidays.add(_parse_date(h))
            except ValueError:
                pass

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
    """
    Find the next or previous occurrence of a specific weekday relative to a date.

    Use this tool when the user asks:
    - What is the next Monday after date X?
    - What was the last Friday before today?
    - When is the coming Saturday?
    - Find the previous Thursday relative to a date.
    - What is the nearest upcoming Tuesday?

    Input:
    - reference_date: YYYY-MM-DD or "today".
    - weekday: name of the target day (case-insensitive).
      Accepted values (English): monday, tuesday, wednesday, thursday, friday, saturday, sunday
      Accepted values (Portuguese): segunda, terça, quarta, quinta, sexta, sábado, domingo
      Accepted abbreviations: mon, tue, wed, thu, fri, sat, sun
    - direction: "next" (default, look forward) or "previous" (look backward).
    - include_reference: if True, the reference date itself can be returned when
      it already falls on the requested weekday. Default is False (always moves
      at least 1 day away).

    Good inputs:
    - reference_date="today", weekday="friday"
    - reference_date="2025-03-10", weekday="segunda", direction="previous"

    Returns a dict with:
    - reference: input reference date ISO
    - weekday_requested: canonical English name of the requested weekday
    - result: ISO date of the found occurrence
    - result_details: full date info for the result
    - days_from_reference: number of calendar days between reference and result
    - direction: "next" or "previous"
    """
    ref = _parse_date(reference_date)
    target_weekday = _parse_weekday(weekday)

    if direction == "next":
        delta = (target_weekday - ref.weekday()) % 7
        if delta == 0 and not include_reference:
            delta = 7
        result = ref + timedelta(days=delta)
    else:  # "previous"
        delta = (ref.weekday() - target_weekday) % 7
        if delta == 0 and not include_reference:
            delta = 7
        result = ref - timedelta(days=delta)

    return {
        "reference": ref.isoformat(),
        "weekday_requested": _WEEKDAY_NAMES_EN[target_weekday],
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
    """
    List all dates within a range, with optional weekday or business-day filtering.

    Use this tool when the user asks:
    - List all Mondays in March 2025.
    - How many Fridays are there between X and Y?
    - Give me all weekdays in a date range.
    - List every Saturday and Sunday in a range.
    - How many times does a specific weekday appear in a month?

    Input:
    - start_date: YYYY-MM-DD or "today" (inclusive).
    - end_date: YYYY-MM-DD or "today" (inclusive).
    - filter_weekdays: optional list of weekday names to include exclusively.
      Accepts English, Portuguese, or abbreviations (same as find_next_weekday).
      Example: ["monday", "friday"] or ["segunda", "sexta"]
    - only_business_days: if True, return only Mon–Fri dates (overrides filter_weekdays).

    Note: to avoid excessively large results, ranges over 2 years (730 days) are rejected.

    Good inputs:
    - start_date="2025-03-01", end_date="2025-03-31", filter_weekdays=["monday"]
    - start_date="today", end_date="2025-12-31", only_business_days=True

    Returns a dict with:
    - start, end: ISO boundary dates
    - total_calendar_days: total days in the range (inclusive)
    - dates: list of ISO date strings matching the filter
    - count: number of matching dates
    - filter_applied: description of the filter used
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    earlier, later = (start, end) if start <= end else (end, start)

    total_calendar = (later - earlier).days + 1
    if total_calendar > 730:
        raise ValueError(
            f"Range of {total_calendar} days is too large. "
            f"Please use a range of 730 days (2 years) or less."
        )

    allowed_weekdays: Optional[set[int]] = None
    filter_description: str

    if only_business_days:
        allowed_weekdays = {0, 1, 2, 3, 4}
        filter_description = "business days (Mon–Fri)"
    elif filter_weekdays:
        allowed_weekdays = {_parse_weekday(w) for w in filter_weekdays}
        names = ", ".join(_WEEKDAY_NAMES_EN[n] for n in sorted(allowed_weekdays))
        filter_description = f"weekdays: {names}"
    else:
        filter_description = "none (all dates)"

    result_dates: list[str] = []
    current = earlier
    while current <= later:
        if allowed_weekdays is None or current.weekday() in allowed_weekdays:
            result_dates.append(current.isoformat())
        current += timedelta(days=1)

    return {
        "start": earlier.isoformat(),
        "end": later.isoformat(),
        "total_calendar_days": total_calendar,
        "dates": result_dates,
        "count": len(result_dates),
        "filter_applied": filter_description,
    }
