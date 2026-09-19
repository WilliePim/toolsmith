# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:50:51+00:00
def run(prefix: str) -> str:
    digits_str = ""
    for c in prefix:
        if c.isalpha():
            digits_str += str(ord(c.upper()) - ord('A') + 10)
        else:
            digits_str += c
    
    # Luhn rule: reading from rightmost digit to the left, double every second digit
    # (the 1st, 3rd, 5th, ... counting from the right, 1-indexed as specified:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)")
    total = 0
    # Let's check US037833100
    # US -> 30 28 -> digits: 3, 0, 2, 8, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # Reversed: 0, 0, 1, 3, 3, 8, 7, 3, 0, 8, 2, 0, 3
    # Index 0 (1st from right): 0*2 = 0
    # Index 1 (2nd from right): 0
    # Index 2 (3rd from right): 1*2 = 2
    # Let's verify standard ISIN Luhn check digit:
    # In standard ISIN check digit calculation, the check digit itself would be at position 0 from right (undoubled).
    # Since we are calculating the check digit, the rightmost digit of the 11-char expanded string is adjacent to the check digit,
    # so it gets multiplied by 2! That matches "(the 1st, 3rd, 5th, ... counting from the right)".
    for i, ch in enumerate(reversed(digits_str)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    
    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)
