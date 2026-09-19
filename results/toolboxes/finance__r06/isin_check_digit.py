# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:41:40+00:00
def run(prefix: str) -> str:
    digits = []
    for char in prefix:
        if char.isalpha():
            digits.append(str(ord(char.upper()) - ord('A') + 10))
        else:
            digits.append(char)
    digit_str = "".join(digits)
    
    # Luhn rule: reading from rightmost digit to left,
    # double every second digit (the 1st, 3rd, 5th, ... counting from the right, 1-indexed as specified:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right),
    # and if a doubled value is more than 9 subtract 9 from it; sum all the resulting digits;
    # the check digit is (10 - sum modulo 10) modulo 10.")
    total = 0
    for i, ch in enumerate(reversed(digit_str)):
        d = int(ch)
        if i % 2 == 0:  # 0th in 0-indexed reversed is 1st counting from the right
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return str(check)
