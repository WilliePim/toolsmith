# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T17:28:02+00:00
import datetime

def run(date: str) -> str:
    parts = [int(p) for p in date.split("-")]
    d = datetime.date(parts[0], parts[1], parts[2])
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}-{iso[2]}"
