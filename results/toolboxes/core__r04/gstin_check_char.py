# toolsmith tool 'gstin_check_char', family 'gstin', written 2026-09-19T17:18:04+00:00
def run(prefix: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    char_to_val = {c: i for i, c in enumerate(chars)}
    
    # Standard GSTIN checksum algorithm (Luhn mod 36 variant):
    # Weights alternate 1, 2, 1, 2... starting at index 0 with weight 1 (or is it?)
    # Wait, let's verify how standard GSTIN checksum works:
    # Let's check the worked example:
    # 22AAAAA0000A1Z -> C
    # 07AABCS1429B1Z -> W
    #
    # Standard Luhn mod 36 for GSTIN:
    # For index i from 0 to 13:
    # weight = 1 if i % 2 == 0 else 2
    # product = val * weight
    # quotient = product // 36
    # remainder = product % 36
    # digit_sum = quotient + remainder
    # total_sum += digit_sum
    # check_val = (36 - (total_sum % 36)) % 36
    # Let's verify this logic against the example:
    # Let's calculate for 22AAAAA0000A1Z:
    # 2 (w=1): 2
    # 2 (w=2): 4
    # A=10 (w=1): 10
    # A=10 (w=2): 20
    # A=10 (w=1): 10
    # A=10 (w=2): 20
    # A=10 (w=1): 10
    # 0 (w=2): 0
    # 0 (w=1): 0
    # 0 (w=2): 0
    # 0 (w=1): 0
    # A=10 (w=2): 20
    # 1 (w=1): 1
    # Z=35 (w=2): 70 -> 70 // 36 = 1, 70 % 36 = 34 -> 1 + 34 = 35
    # Sum: 2 + 4 + 10 + 20 + 10 + 20 + 10 + 0 + 0 + 0 + 0 + 20 + 1 + 35 = 132
    # 132 % 36 = 24
    # (36 - 24) % 36 = 12
    # chars[12] = 'C'! Exactly 'C'!
    
    total = 0
    for i, c in enumerate(prefix):
        val = char_to_val[c.upper()]
        weight = 1 if i % 2 == 0 else 2
        prod = val * weight
        total += (prod // 36) + (prod % 36)
    
    check_val = (36 - (total % 36)) % 36
    return chars[check_val]
