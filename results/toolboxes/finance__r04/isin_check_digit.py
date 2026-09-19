# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:23:02+00:00
def run(prefix: str) -> str:
    # Convert prefix characters to digits: A=10, ..., Z=35
    digits = []
    for c in prefix.upper():
        if c.isdigit():
            digits.append(int(c))
        elif 'A' <= c <= 'Z':
            val = ord(c) - ord('A') + 10
            digits.append(val // 10)
            digits.append(val % 10)
        else:
            raise ValueError(f"Invalid character: {c}")

    # Luhn rule: reading from rightmost to left, double every second digit:
    # "reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Notice: "1st, 3rd, 5th... counting from the right" means index from right: 0-th (first from right), 2-nd (third from right), etc.
    # Let's verify with US037833100 -> 5.
    # US -> U=30, S=28 -> 3, 0, 2, 8
    # 0 3 7 8 3 3 1 0 0
    # Combined string: 3 0 2 8 0 3 7 8 3 3 1 0 0
    # Length: 13 digits.
    # Right to left (1-based index from right: 1st, 2nd, 3rd, ...):
    # 1st from right (rightmost): 0 -> doubled? Wait! The prompt says:
    # "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Wait, usually Luhn on full number doubles odd positions from right excluding check digit, meaning check digit is at pos 0 (or 1st from right), so the digit before it is 2nd from right.
    # BUT here, the check digit is NOT appended yet!
    # Let's check US037833100:
    # If full ISIN is US0378331005:
    # full digits: 3 0 2 8 0 3 7 8 3 3 1 0 0 [5]
    # In standard Luhn for ISIN:
    # The check digit would be at position 1 (from right). The digit before it (the rightmost of prefix) is position 2 from right.
    # But wait, what does the prompt say?
    # "Then apply the Luhn rule to that string: reading from the rightmost digit to the left, double every second digit (the 1st, 3rd, 5th, ... counting from the right), and if a doubled value is more than 9 subtract 9 from it; sum all the resulting digits; the check digit is (10 - sum modulo 10) modulo 10."
    # Let's calculate:
    # Digits from right:
    # pos 1: 0 -> doubled: 0
    # pos 2: 0 -> not doubled: 0
    # pos 3: 1 -> doubled: 2
    # pos 4: 3 -> not doubled: 3
    # pos 5: 3 -> doubled: 6
    # pos 6: 8 -> not doubled: 8
    # pos 7: 7 -> doubled: 14 -> 5
    # pos 8: 3 -> not doubled: 3
    # pos 9: 0 -> doubled: 0
    # pos 10: 8 -> not doubled: 8
    # pos 11: 2 -> doubled: 4
    # pos 12: 0 -> not doubled: 0
    # pos 13: 3 -> doubled: 6
    # Sum = 0 + 0 + 2 + 3 + 6 + 8 + 5 + 3 + 0 + 8 + 4 + 0 + 6 = 45.
    # (10 - 45 % 10) % 10 = (10 - 5) % 10 = 5!
    # Exactly 5!
    total = 0
    for i, d in enumerate(reversed(digits)):
        # i = 0 corresponds to 1st from right, i = 1 is 2nd, etc.
        if i % 2 == 0:  # 1st, 3rd, 5th... from right (0-indexed: 0, 2, 4...)
            val = d * 2
            if val > 9:
                val -= 9
            total += val
        else:
            total += d
    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)
