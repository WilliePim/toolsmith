# toolsmith tool 'trading_session', family 'sessions', written 2026-09-19T18:20:11+00:00
from datetime import datetime, timedelta

def run(start: str, n: int, closures: list) -> str:
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    holidays = set(closures)
    count = 0
    while count < n:
        cur += timedelta(days=1)
        # weekday(): Monday is 0, Sunday is 6
        if cur.weekday() < 5 and cur.strftime("%Y-%m-%d") not in holidays:
            count += 1
    return cur.strftime("%Y-%m-%d")
