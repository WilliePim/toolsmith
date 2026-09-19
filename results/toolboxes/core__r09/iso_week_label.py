# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T18:05:01+00:00
import datetime

def run(date: str) -> str:
    d = datetime.date.fromisoformat(date)
    year, week, weekday = d.isocalendar()
    return f"{year:04d}-W{week:02d}-{weekday}"
