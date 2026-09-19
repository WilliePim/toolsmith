# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T17:10:04+00:00
import datetime

def run(date: str) -> str:
    d = datetime.date.fromisoformat(date)
    year, week, day = d.isocalendar()
    return f"{year:04d}-W{week:02d}-{day}"
