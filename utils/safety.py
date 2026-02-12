import re
from jamo import h2j, j2hcj
BAD_WORDS = [
    r"시발", r"씨발", r"ㅅㅂ", r"ㅆㅂ", r"쉬발", r"슈발",
    r"병신", r"ㅄ", r"ㅂㅅ",
    r"미친", r"ㅁㅊ",
    r"애미", r"애비", r"느금", r"니미",
    r"개새끼", r"개새",
    r"꺼져", r"닥쳐", r"존나", r"졸라",
    r"섹스", r"섹1스", r"ㅅㅅ", r"야동", r"망가", r"자위", r"딜도", r"콘돔", r"페니스", r"바이브레이터", r"오르가즘", r"사정",
    r"성관계", r"유두", r"클리", r"잠자리", r"강간", r"윤간", r"수간", r"근친", r"로리", r"쇼타",
    r"좆", r"씹", r"보지", r"자지", r"가슴", r"엉덩이",
    r"한남", r"한녀", r"맘충", r"틀딱", r"쪽발", r"짱깨",
    r"자살", r"죽어", r"살자", r"나가뒤져", r"칼빵",
    r"tlqkf", r"qudtls",    r"rotorl", r"ekrcj", r"rjwu",    r"whssk", r"whffk",    r"wlfkf", r"enlwu"]
def analyze_korean(text):
    jamo_str = j2hcj(h2j(text))
    return jamo_str
def check_message(content: str) -> bool:
    clean_content = content.replace(" ", "").lower()
    try:
        from jamo import h2j, j2hcj
        jamo_content = j2hcj(h2j(clean_content))
    except ImportError:
        jamo_content = clean_content
    for pattern in BAD_WORDS:
        if re.search(pattern, clean_content):
            return True
        if re.search(pattern, jamo_content):
            return True
    return False
def check_command_safety(content: str) -> bool:
    if check_message(content):
        return True
    return False
def get_warning_message() -> str:
    import random
    msgs = [
        "그런 말씀은 너무해요... 요미가 슬퍼져요. (｡•́︿•̀｡)",
        "예쁜 말만 쓰기로 약속했잖아요! 흥! ( *｀ω´)",
        "교주님, 언어가 너무 거칠어요! 조금만 부드럽게 말씀해주세요.",
        "그런 말은 요미가 배우면 안 된단 말이에요... (´;ω;｀)",
        "헙... 방금 그 말은 못 들은 걸로 할게요! 다시 예쁘게 말씀해주실 거죠?"
    ]
    return random.choice(msgs)