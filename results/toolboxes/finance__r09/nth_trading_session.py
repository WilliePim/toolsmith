# toolsmith tool 'nth_trading_session', family 'sessions', written 2026-09-19T18:10:52+00:00
import datetime

def run(start: str, n: int, closures: list) -> str:
    closure_set = set(closures)
    curr = datetime.date.fromisoformat(start)
    count = 0
    while count < n:
        curr += datetime.timedelta(days=1)
        # Weekday: Monday is 0, Sunday is 6
        if curr.weekday() < 5 and curr.isoformat() not in closure_set:
            count += 1
    return curr.isoformat()
