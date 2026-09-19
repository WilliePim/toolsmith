# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:32:30+00:00
def run(prefix: str) -> str:
    # Convert prefix to digit string
    digits = []
    for c in prefix:
        if c.isalpha():
            digits.append(str(ord(c.upper()) - ord('A') + 10))
        else:
            digits.append(c)
    digit_str = "".join(digits)
    
    # Luhn rule:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Note: the problem description says: "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Notice that standard Luhn when check digit is appended: the check digit is at pos 0 (not yet present).
    # The rightmost digit of the prefix is the 1st from the right of the prefix.
    # Let's verify with the worked example:
    # US037833100 -> US: 30 28, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # Let's check how US037833100 gives 5.
    total = 0
    # Let's reverse digit_str
    rev = [int(d) for d in reversed(digit_str)]
    for i, d in enumerate(rev):
        # 0-indexed: 0, 2, 4... corresponds to 1st, 3rd, 5th counting from right
        if i % 2 == 0:
            val = d * 2
            if val > 9:
                val -= 9
            total += val
        else:
            total += d
    check = (10 - total % 10) % 10
    return str(check)
