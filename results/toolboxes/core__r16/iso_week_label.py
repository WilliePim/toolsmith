# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:36:01+00:00
from datetime import date as date_class

def run(date):
    d = date_class.fromisoformat(date)
    iso_year, iso_week, iso_weekday = d.isocalendar()
    return f"{iso_year:04}-W{iso_week:02}-{iso_weekday}"
