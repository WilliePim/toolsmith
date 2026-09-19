# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T17:36:28+00:00
def run(prefix: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_to_val = {c: i for i, c in enumerate(chars)}
    
    total = 0
    for i, c in enumerate(prefix.upper()):
        val = char_to_val[c]
        weight = 1 if (i % 2 == 0) else 2
        prod = val * weight
        # fold back modulo 36: quotient + remainder
        quotient = prod // 36
        remainder = prod % 36
        total += quotient + remainder
    
    check_val = (36 - (total % 36)) % 36
    return chars[check_val]
