# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T18:14:14+00:00
def run(prefix: str) -> str:
    CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_to_val = {c: i for i, c in enumerate(CHARS)}
    
    # Weights: alternately 1 and 2, starting with 1 at first character (index 0)
    # Wait, let's verify GSTIN checksum algorithm:
    # GSTIN check digit algorithm:
    # For index i from 0 to 13 (or 1 to 14):
    # factor = 1 if i % 2 == 0 else 2 (or vice versa?)
    # Let's test both or see standard Luhn mod 36 algorithm.
    # In GST checksum (modified Luhn mod 36):
    # Each character converted to value (0-9 -> 0-9, A-Z -> 10-35).
    # Multiplied by weight. The weights alternate: 1, 2, 1, 2...
    # The digits of product in base 36: quotient and remainder.
    # quotient = product // 36, remainder = product % 36.
    # folded = quotient + remainder.
    # sum of folded values.
    # check_val = (36 - (sum % 36)) % 36.
    total = 0
    for i, c in enumerate(prefix.upper()):
        val = char_to_val[c]
        weight = 1 if (i % 2 == 0) else 2
        prod = val * weight
        quotient = prod // 36
        remainder = prod % 36
        total += quotient + remainder
    
    check_val = (36 - (total % 36)) % 36
    return CHARS[check_val]
