# toolsmith tool 'nth_trading_session', family 'sessions', written 2026-09-19T17:51:26+00:00
from datetime import datetime, timedelta

def run(start: str, n: int, closures: list) -> str:
    holiday_set = set(closures)
    cur = datetime.strptime(start, "%Y-%m-%d")
    count = 0
    while count < n:
        cur += timedelta(days=1)
        # Monday is 0, Sunday is 6
        if cur.weekday() < 5:
            cur_str = cur.strftime("%Y-%m-%d")
            if cur_str not in holiday_set:
                count += 1
    return cur.strftime("%Y-%m-%d")
