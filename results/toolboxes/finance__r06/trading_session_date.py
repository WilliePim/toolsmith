# toolsmith tool 'trading_session_date', family 'sessions', written 2026-09-19T17:42:44+00:00
from datetime import datetime, timedelta

def run(start: str, n: int, closures: list) -> str:
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    closure_set = set(closures)
    count = 0
    while count < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime("%Y-%m-%d") not in closure_set:
            count += 1
    return cur.strftime("%Y-%m-%d")
