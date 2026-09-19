# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T16:55:05+00:00
def run(prefix: str) -> str:
    digits = []
    for c in prefix:
        if c.isdigit():
            digits.append(int(c))
        elif c.isupper():
            val = ord(c) - ord('A') + 10
            digits.extend([val // 10, val % 10])
        elif c.islower():
            val = ord(c.upper()) - ord('A') + 10
            digits.extend([val // 10, val % 10])
            
    # Luhn rule: reading from rightmost digit to the left, double every second digit
    # Notice the prompt: "(the 1st, 3rd, 5th, ... counting from the right)"
    # Wait, let's carefully check:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Usually, if the check digit was appended at position 0 from right (the rightmost), then the prefix's rightmost digit would be position 1 (odd position, doubled).
    # Indeed, "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Let's verify US037833100:
    # U=30, S=28, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # Digits: 3, 0, 2, 8, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # Rightmost is 0 (1st from right).
    # 1st from right: 0 * 2 = 0
    # 2nd from right: 0 -> 0
    # 3rd from right: 1 * 2 = 2
    # 4th: 3 -> 3
    # 5th: 3 * 2 = 6
    # 6th: 8 -> 8
    # 7th: 7 * 2 = 14 -> 14 - 9 = 5
    # 8th: 3 -> 3
    # 9th: 0 * 2 = 0
    # 10th: 8 -> 8
    # 11th: 2 * 2 = 4
    # 12th: 0 -> 0
    # 13th: 3 * 2 = 6
    # Sum: 0 + 0 + 2 + 3 + 6 + 8 + 5 + 3 + 0 + 8 + 4 + 0 + 6 = 45.
    # Check digit: (10 - 45 % 10) % 10 = (10 - 5) % 10 = 5.
    # Matches the worked example "5"!
    
    total = 0
    for idx, d in enumerate(reversed(digits)):
        if idx % 2 == 0:  # 0th index in reversed is 1st counting from right
            val = d * 2
            if val > 9:
                val -= 9
            total += val
        else:
            total += d
            
    check = (10 - (total % 10)) % 10
    return str(check)
