# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-19T17:00:28+00:00
import datetime

def run(date: str) -> str:
    parts = [int(p) for p in date.split("-")]
    d = datetime.date(parts[0], parts[1], parts[2])
    iso = d.isocalendar()
    return "%04d-W%02d-%d" % (iso[0], iso[1], iso[2])
