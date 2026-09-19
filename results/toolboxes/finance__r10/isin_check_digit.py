# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T18:19:06+00:00
def run(prefix: str) -> str:
    # Convert prefix characters to digits:
    # A=10, ..., Z=35, digits stay digits
    digits_str = ""
    for char in prefix:
        if char.isdigit():
            digits_str += char
        elif char.isalpha():
            digits_str += str(ord(char.upper()) - ord('A') + 10)
    
    # Luhn rule:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Note: 1st, 3rd, 5th counting from the right means odd index from the right (1-based), i.e. the rightmost digit is doubled, then 3rd from right is doubled, etc.
    # Let's verify with the worked example: US037833100 -> check digit 5.
    # US -> U=30, S=28 -> 3028
    # 037833100
    # Total string: 3028037833100
    # Digits from right:
    # pos 1 (from right): '0' -> doubled: 0*2 = 0
    # pos 2: '0' -> unchanged: 0
    # pos 3: '1' -> doubled: 2
    # pos 4: '3' -> unchanged: 3
    # pos 5: '3' -> doubled: 6
    # pos 6: '8' -> unchanged: 8
    # pos 7: '7' -> doubled: 14 -> 14-9 = 5
    # pos 8: '3' -> unchanged: 3
    # pos 9: '0' -> doubled: 0
    # pos 10: '8' -> unchanged: 8
    # pos 11: '2' -> doubled: 4
    # pos 12: '0' -> unchanged: 0
    # pos 13: '3' -> doubled: 6
    # Sum: 0 + 0 + 2 + 3 + 6 + 8 + 5 + 3 + 0 + 8 + 4 + 0 + 6 = 45.
    # check digit: (10 - 45 % 10) % 10 = (10 - 5) % 10 = 5.
    # Exactly matches!
    total = 0
    for i, ch in enumerate(reversed(digits_str)):
        d = int(ch)
        if i % 2 == 0:  # 1st, 3rd, 5th from right (0-indexed: 0, 2, 4...)
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return str(check)
