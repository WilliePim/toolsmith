# toolsmith tool 'iso_week_label', family 'isoweek', written 2026-09-20T13:36:23+00:00
import datetime

def run(date):
    # Parse the date string
    year, month, day = map(int, date.split('-'))
    date_obj = datetime.date(year, month, day)
    
    # Get ISO calendar info
    iso_year, iso_week, iso_weekday = date_obj.isocalendar()
    
    # Format: YYYY-Www-D
    # iso_week needs to be zero-padded to two digits (e.g., '01')
    return f"{iso_year}-W{iso_week:02}-{iso_weekday}"
