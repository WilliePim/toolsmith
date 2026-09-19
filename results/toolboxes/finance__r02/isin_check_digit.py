# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T17:04:58+00:00
def run(prefix: str) -> str:
    # Convert prefix to digits
    digits = []
    for char in prefix:
        if char.isalpha():
            val = ord(char.upper()) - ord('A') + 10
            digits.extend([int(d) for d in str(val)])
        elif char.isdigit():
            digits.append(int(char))
        else:
            raise ValueError(f"Invalid character: {char}")
    
    # Luhn algorithm: reading from the rightmost digit to the left,
    # "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Note: Task description says: "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Wait, usually the check digit is the 0th from the right (if included), but here check digit is not yet appended.
    # The prompt explicitly specifies: "(the 1st, 3rd, 5th, ... counting from the right)"
    # Let's verify with the worked example: US037833100 -> check digit 5.
    
    # Let's check US037833100:
    # U=30, S=28, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # string of digits: 3, 0, 2, 8, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # Let's see: from right:
    # index from right (1-based):
    # 1st (rightmost): 0 -> doubled is 0
    # 2nd: 0 -> not doubled (0)
    # 3rd: 1 -> doubled is 2
    # 4th: 3 -> 3
    # 5th: 3 -> doubled is 6
    # 6th: 8 -> 8
    # 7th: 7 -> doubled is 14 -> 14-9=5
    # 8th: 3 -> 3
    # 9th: 0 -> doubled is 0
    # 10th: 8 -> 8
    # 11th: 2 -> doubled is 4
    # 12th: 0 -> 0
    # 13th: 3 -> doubled is 6
    # Sum: 6 + 0 + 4 + 8 + 0 + 3 + 5 + 8 + 6 + 3 + 2 + 0 + 0 = 35.
    # Check digit: (10 - 35 % 10) % 10 = (10 - 5) % 10 = 5! Exactly 5!
    
    total = 0
    for i, d in enumerate(reversed(digits)):
        # i = 0 corresponds to 1st from right
        if i % 2 == 0:  # 1st, 3rd, 5th, etc.
            doubled = d * 2
            if doubled > 9:
                doubled -= 9
            total += doubled
        else:
            total += d
            
    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)
