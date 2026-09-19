# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T17:54:09+00:00
def run(prefix: str) -> str:
    CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_map = {c: i for i, c in enumerate(CHARS)}
    
    total = 0
    for i, char in enumerate(prefix):
        val = char_map[char.upper()]
        weight = 1 if (i % 2 == 0) else 2
        prod = val * weight
        quotient = prod // 36
        remainder = prod % 36
        total += quotient + remainder
        
    check_val = (36 - (total % 36)) % 36
    return CHARS[check_val]
