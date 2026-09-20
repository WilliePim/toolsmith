# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:34:29+00:00
import datetime

def run(date: str) -> str:
    year, month, day = map(int, date.split('-'))
    date_obj = datetime.date(year, month, day)
    iso_year, iso_week, iso_weekday = date_obj.isocalendar()
    return f"{iso_year}-W{iso_week:02}-{iso_weekday}"
