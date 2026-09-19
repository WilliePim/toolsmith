# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T17:46:41+00:00
from datetime import datetime

def run(date: str) -> str:
    dt = datetime.strptime(date, "%Y-%m-%d")
    iso_year, iso_week, iso_weekday = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}-{iso_weekday}"
