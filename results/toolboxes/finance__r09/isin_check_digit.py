# toolsmith tool 'isin_check_digit', family 'isin', written 2026-09-19T18:09:10+00:00
def run(prefix: str) -> str:
    # 1. Convert each char to digits: letters A-Z -> 10-35, digits stay as is
    digits_str = ""
    for char in prefix.upper():
        if '0' <= char <= '9':
            digits_str += char
        elif 'A' <= char <= 'Z':
            digits_str += str(ord(char) - ord('A') + 10)
    
    # 2. Apply Luhn rule: reading from rightmost digit to left,
    # "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Notice the prompt says: "(the 1st, 3rd, 5th, ... counting from the right)"
    # Let's check US037833100:
    # U=30, S=28 -> "3028037833100"
    # Wait, 1st from right is 0. Does 1st get doubled or does every second digit get doubled?
    # Let's re-read carefully: "double every second digit (the 1st, 3rd, 5th, ... counting from the right)"
    # Usually in Luhn on an 11-char prefix where the check digit is at the end (position 12),
    # the check digit would be at 0th from right (if check digit is included).
    # Without check digit, the rightmost digit of the converted string is multiplied by 2!
    # Because check digit is at weight 1, so the digit immediately to its left has weight 2, next weight 1, next weight 2...
    # That's why prompt says: "(the 1st, 3rd, 5th, ... counting from the right)" with 1-based indexing from the right!
    # Let's verify US037833100:
    # U=30, S=28, 0, 3, 7, 8, 3, 3, 1, 0, 0
    # string: 3,0,2,8,0,3,7,8,3,3,1,0,0
    # Reversing: 0, 0, 1, 3, 3, 8, 7, 3, 0, 8, 2, 0, 3
    # 1st: 0 * 2 = 0
    # 2nd: 0
    # 3rd: 1 * 2 = 2
    # 4th: 3
    # 5th: 3 * 2 = 6
    # 6th: 8
    # 7th: 7 * 2 = 14 -> 14-9 = 5
    # 8th: 3
    # 9th: 0 * 2 = 0
    # 10th: 8
    # 11th: 2 * 2 = 4
    # 12th: 0
    # 13th: 3 * 2 = 6
    # Sum = 0 + 0 + 2 + 3 + 6 + 8 + 5 + 3 + 0 + 8 + 4 + 0 + 6 = 45.
    # (10 - 45 % 10) % 10 = (10 - 5) % 10 = 5! Exactly matches worked example US037833100 -> "5".
    
    total = 0
    # reversed digits: index 0 is 1st from right, index 1 is 2nd from right, etc.
    for i, ch in enumerate(reversed(digits_str)):
        d = int(ch)
        if i % 2 == 0:  # 1st, 3rd, 5th... from right (0-indexed even)
            d *= 2
            if d > 9:
                d -= 9
        total += d
        
    check = (10 - (total % 10)) % 10
    return str(check)
