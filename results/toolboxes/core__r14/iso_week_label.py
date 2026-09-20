# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:35:18+00:00
from datetime import datetime

def run(date: str) -> str:
    dt = datetime.strptime(date, "%Y-%m-%d")
    year, week, weekday = dt.isocalendar()
    return f"{year}-W{week:02}-{weekday}"
