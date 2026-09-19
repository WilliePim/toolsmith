# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T16:52:40+00:00
import datetime

def run(date: str) -> str:
    d = datetime.date.fromisoformat(date)
    iso_year, iso_week, iso_day = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}-{iso_day}"
