# toolsmith tool 'gstin_checksum', family 'gstin', written 2026-09-19T16:59:45+00:00
def run(prefix: str) -> str:
    CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_to_val = {c: i for i, c in enumerate(CHARS)}
    
    # Checksum algorithm for GSTIN:
    # 14 chars. Weights alternate: 1, 2, 1, 2, ...
    # For each char i (0-indexed):
    # factor = 1 if i % 2 == 0 else 2
    # product = val * factor
    # quotient = product // 36
    # remainder = product % 36
    # sum += quotient + remainder
    # Then remainder = sum % 36
    # check_val = (36 - remainder) % 36
    # check_char = CHARS[check_val]
    
    total = 0
    for i, ch in enumerate(prefix):
        val = char_to_val[ch]
        factor = 1 if i % 2 == 0 else 2
        prod = val * factor
        total += (prod // 36) + (prod % 36)
        
    check_val = (36 - (total % 36)) % 36
    return CHARS[check_val]
