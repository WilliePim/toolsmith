# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T16:51:46+00:00
def run(prefix: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    val_map = {c: i for i, c in enumerate(chars)}
    
    total = 0
    for i, ch in enumerate(prefix):
        val = val_map[ch.upper()]
        weight = 1 if (i % 2 == 0) else 2
        product = val * weight
        # Luhn mod 36 digit folding: quotient + remainder in base 36
        folded = (product // 36) + (product % 36)
        total += folded
        
    remainder = total % 36
    check_val = (36 - remainder) % 36
    return chars[check_val]
