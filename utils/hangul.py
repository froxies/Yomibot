def get_initials(text):
    CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
    result = []
    for char in text:
        if '가' <= char <= '힣':
            char_code = ord(char) - 0xAC00
            chosung_index = char_code // 588
            result.append(CHOSUNG_LIST[chosung_index])
        else:
            result.append(char)
    return "".join(result)
def is_hangul(text):
    for char in text:
        if not ('가' <= char <= '힣'):
            return False
    return True