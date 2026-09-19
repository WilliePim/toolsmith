# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T18:15:09+00:00
import datetime

def run(date: str) -> str:
    dt = datetime.date.fromisoformat(date)
    iso_year, iso_week, iso_day = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}-{iso_day}"
