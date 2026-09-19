# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:13:47+00:00
def run(prefix: str) -> str:
    # Convert prefix to digit string
    digits = []
    for c in prefix:
        if c.isdigit():
            digits.append(c)
        elif c.isalpha():
            val = ord(c.upper()) - ord('A') + 10
            digits.append(str(val))
        else:
            raise ValueError(f"Invalid character: {c}")
    digit_str = "".join(digits)
    
    # Luhn rule on the digit string:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Note: "the 1st, 3rd, 5th, ... counting from the right" means the rightmost is doubled, or does it?
    # Let's check the wording:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right), and if a doubled value is more than 9 subtract 9 from it"
    # Notice: normally check digit is at the right, but here the check digit is NOT YET PRESENT.
    # If the check digit were present (position 0 from right), then position 1 from right (the rightmost of the 11-char expanded digits) would be doubled!
    # So counting from the right of the 11-char digit string:
    # 1st from right (i.e. index -1) is doubled, 2nd is not, 3rd is doubled, etc.
    total = 0
    for idx, ch in enumerate(reversed(digit_str)):
        d = int(ch)
        if idx % 2 == 0:  # 1st from right (0-indexed 0, 2, 4...)
            d = d * 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return str(check)
