# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T17:18:39+00:00
import datetime

def run(date: str) -> str:
    dt = datetime.date.fromisoformat(date)
    year, week, weekday = dt.isocalendar()
    return f"{year:04d}-W{week:02d}-{weekday}"
