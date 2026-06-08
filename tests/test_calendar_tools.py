from datetime import date

import pytest

from app.tools import calendar_tools as cal


def test_get_today_info():
    info = cal.get_today_info.invoke({})
    assert info["iso"] == date.today().isoformat()
    assert 1 <= info["quarter"] <= 4
    assert isinstance(info["is_leap_year"], bool)


def test_get_date_details_known_date():
    info = cal.get_date_details.invoke({"date_str": "2024-02-29"})
    assert info["is_leap_year"] is True
    assert info["weekday_name_en"] == "Thursday"
    assert info["day_of_year"] == 60


def test_calculate_date_difference():
    d = cal.calculate_date_difference.invoke(
        {"start_date": "2025-01-01", "end_date": "2025-01-08"}
    )
    assert d["total_days"] == 7
    assert d["complete_weeks"] == 1
    # Ordem não importa — span sempre positivo.
    d2 = cal.calculate_date_difference.invoke(
        {"start_date": "2025-01-08", "end_date": "2025-01-01"}
    )
    assert d2["total_days"] == 7


def test_shift_date():
    r = cal.shift_date.invoke({"base_date": "2025-03-15", "amount": 10, "unit": "days"})
    assert r["result"] == "2025-03-25"
    r2 = cal.shift_date.invoke({"base_date": "2025-01-31", "amount": 1, "unit": "months"})
    assert r2["result"] == "2025-02-28"  # clamp para o último dia do mês


def test_count_and_add_business_days():
    # 2025-03-17 (seg) a 2025-03-21 (sex) = 5 dias úteis, 0 fim de semana.
    c = cal.count_business_days.invoke(
        {"start_date": "2025-03-17", "end_date": "2025-03-21"}
    )
    assert c["business_days"] == 5
    assert c["weekend_days"] == 0
    # Sexta + 1 dia útil = segunda.
    a = cal.add_business_days.invoke({"start_date": "2025-03-14", "business_days": 1})
    assert a["result"] == "2025-03-17"


def test_invalid_date_raises():
    with pytest.raises(ValueError):
        cal.get_date_details.invoke({"date_str": "not-a-date"})


def test_date_info_kept_and_trimmed_fields():
    info = cal.get_today_info.invoke({})
    # Campos mantidos (úteis).
    for k in ("iso", "quarter", "is_leap_year", "weekday_name_pt", "day_of_year",
              "days_remaining_in_month", "month_start", "year_end", "iso_week_number"):
        assert k in info
    # Campos removidos no enxugamento (redundantes/raros).
    for k in ("unix_timestamp", "quarter_label", "is_weekday", "formatted_us",
              "days_elapsed_in_year", "is_first_day_of_month", "iso_week_year"):
        assert k not in info


def test_date_difference_age_breakdown():
    d = cal.calculate_date_difference.invoke(
        {"start_date": "2000-01-15", "end_date": "2001-03-20"}
    )
    assert d["complete_years"] == 1
    assert d["remaining_months_after_years"] == 2
    assert d["remaining_days_after_years_months"] == 5
    assert "approximate_months" not in d  # removido


def test_list_dates_in_range_weekday_filter():
    # Março/2025 tem 5 segundas-feiras (3, 10, 17, 24, 31).
    r = cal.list_dates_in_range.invoke(
        {"start_date": "2025-03-01", "end_date": "2025-03-31", "filter_weekdays": ["monday"]}
    )
    assert r["count"] == 5
    assert r["dates"][0] == "2025-03-03"
