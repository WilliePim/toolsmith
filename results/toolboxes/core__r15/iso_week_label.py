# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:35:34+00:00
import datetime

def run(date: str) -> str:
    dt = datetime.datetime.strptime(date, "%Y-%m-%d")
    iso_year, iso_week, iso_day = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}-{iso_day}"
