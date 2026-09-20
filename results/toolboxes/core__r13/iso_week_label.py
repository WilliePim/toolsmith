# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:34:55+00:00
import datetime

def run(date: str) -> str:
    y, m, d = map(int, date.split('-'))
    dt = datetime.date(y, m, d)
    iso_year, iso_week, iso_weekday = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}-{iso_weekday}"
