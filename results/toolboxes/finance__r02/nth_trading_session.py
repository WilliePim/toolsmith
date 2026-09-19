# toolsmith tool 'nth_trading_session', family 'sessions', written 2026-09-19T17:05:35+00:00
import datetime

def run(start: str, n: int, closures: list) -> str:
    closure_set = set(closures)
    cur = datetime.date.fromisoformat(start)
    count = 0
    while count < n:
        cur += datetime.timedelta(days=1)
        # weekday(): Monday is 0 and Sunday is 6
        if cur.weekday() < 5 and cur.isoformat() not in closure_set:
            count += 1
    return cur.isoformat()
