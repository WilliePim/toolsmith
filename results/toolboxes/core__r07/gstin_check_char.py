# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T17:45:34+00:00
def run(prefix: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_map = {c: i for i, c in enumerate(chars)}
    
    total = 0
    for i, c in enumerate(prefix):
        val = char_map[c]
        weight = 1 if i % 2 == 0 else 2
        prod = val * weight
        # folded back modulo 36: quotient + remainder
        quotient = prod // 36
        remainder = prod % 36
        total += quotient + remainder
        
    remainder = total % 36
    check_val = (36 - remainder) % 36
    return chars[check_val]
