# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T18:03:59+00:00
def run(prefix: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_map = {c: i for i, c in enumerate(chars)}
    
    total = 0
    for i, ch in enumerate(prefix):
        val = char_map[ch.upper()]
        factor = 1 if (i % 2 == 0) else 2
        prod = val * factor
        # "folded back modulo 36": sum of base-36 digits of prod, i.e., prod // 36 + prod % 36
        folded = (prod // 36) + (prod % 36)
        total += folded
        
    rem = total % 36
    check_val = (36 - rem) % 36
    return chars[check_val]
