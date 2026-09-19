# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:58:38+00:00
def run(prefix: str) -> str:
    # Convert prefix to digits
    digits = []
    for c in prefix:
        if c.isalpha():
            digits.append(str(ord(c.upper()) - ord('A') + 10))
        else:
            digits.append(c)
    digit_str = "".join(digits)
    
    # Luhn rule: reading from rightmost to left, double every second digit
    # Notice the prompt: "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Let's verify with US037833100 -> "5".
    # US -> U=30, S=28 -> 3028037833100
    # Let's check the wording: "the 1st, 3rd, 5th, ... counting from the right"
    # Wait, usually Luhn on the 11-prefix without check digit:
    # If the check digit were at index 0 (from right), then the rightmost digit of prefix would be index 1 (the 1st from right to be doubled!)
    # Let's carefully trace US037833100:
    # Digits: 3 0 2 8 0 3 7 8 3 3 1 0 0
    # From right to left:
    # positions 1, 2, 3... (1-indexed from right):
    # pos 1: 0 (doubled: 0)
    # pos 2: 0 (undoubled: 0)
    # pos 3: 1 (doubled: 2)
    # pos 4: 3 (undoubled: 3)
    # pos 5: 3 (doubled: 6)
    # pos 6: 8 (undoubled: 8)
    # pos 7: 7 (doubled: 14 -> 5 or sum of digits 1+4=5, 14-9=5)
    # pos 8: 3 (undoubled: 3)
    # pos 9: 0 (doubled: 0)
    # pos 10: 8 (undoubled: 8)
    # pos 11: 2 (doubled: 4)
    # pos 12: 0 (undoubled: 0)
    # pos 13: 3 (doubled: 6)
    # Sum: 6 + 0 + 4 + 8 + 0 + 3 + 5 + 8 + 6 + 3 + 2 + 0 + 0 = 45.
    # Check digit = (10 - 45 % 10) % 10 = (10 - 5) % 10 = 5.
    # Matches the worked example!
    
    total = 0
    # reversed digits:
    rev = list(reversed(digit_str))
    for i, ch in enumerate(rev):
        d = int(ch)
        if i % 2 == 0:  # 0th in 0-indexed is 1st from right
            d *= 2
            if d > 9:
                d -= 9
        total += d
        
    check = (10 - (total % 10)) % 10
    return str(check)
