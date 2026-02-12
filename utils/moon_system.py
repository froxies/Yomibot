import datetime
import random
import utils.time_utils as time_utils
MOON_PHASES = {
    "신월": {"multi": 1.0, "affinity": 1.5, "desc": "새로운 시작의 달입니다. 요미가 더 의지하고 싶어합니다."},
    "초승달": {"multi": 1.1, "affinity": 1.0, "desc": "조금씩 빛이 차오르는 달입니다. 수집 효율이 약간 상승합니다."},
    "상현달": {"multi": 1.3, "affinity": 1.0, "desc": "절반이 차오른 달입니다. 수집 효율이 상승합니다."},
    "보름달": {"multi": 1.5, "affinity": 1.2, "desc": "가장 밝게 빛나는 달입니다. 모든 수집 보상이 대폭 상승합니다!"},
    "하현달": {"multi": 1.2, "affinity": 1.0, "desc": "조금씩 기울어가는 달입니다. 여유로운 수집이 가능합니다."},
    "그믐달": {"multi": 1.0, "affinity": 1.3, "desc": "어두운 밤을 지키는 달입니다. 요미와의 깊은 대화에 집중하세요."}
}
def get_current_moon_phase():
    now = time_utils.get_kst_now()
    day_cycle = now.day % 30
    if day_cycle < 5: return "신월"
    elif day_cycle < 10: return "초승달"
    elif day_cycle < 15: return "상현달"
    elif day_cycle < 20: return "보름달"
    elif day_cycle < 25: return "하현달"
    else: return "그믐달"
RECIPES = {
    "호박 스프": {
        "ingredients": {"호박": 2, "우유": 1},
        "result_desc": "속을 따뜻하게 데워주는 달콤한 스프입니다. (원정대 공격력 +20% / 호감도 +50)",
        "rarity": "Common",
        "effect": "expedition_buff",
        "value": 50
    },
    "달떡": {
        "ingredients": {"쌀": 3, "꿀": 1},
        "result_desc": "요미가 가장 좋아하는 간식입니다. (탐색 쿨다운 초기화 / 호감도 +500)",
        "rarity": "Uncommon",
        "effect": "scavenge_reset",
        "value": 500
    },
    "고급 낚시 미끼": {
        "ingredients": {"작은 물고기": 3, "약초": 1},
        "result_desc": "더 크고 아름다운 물고기를 유혹합니다. (낚시 보너스 상승)",
        "rarity": "Rare",
        "effect": "fishing_buff"
    },
    "별빛 조명": {
        "ingredients": {"빛나는 조각": 5, "철광석": 10},
        "result_desc": "정원에 배치할 수 있는 아름다운 조명입니다.",
        "rarity": "Epic",
        "effect": "furniture"
    },
    "달토끼 인형": {
        "ingredients": {"비단": 2, "솜뭉치": 5},
        "result_desc": "정원에 배치 가능한 귀여운 인형입니다.",
        "rarity": "Uncommon",
        "effect": "furniture"
    },
    "별무늬 카펫": {
        "ingredients": {"별가루": 10, "양털": 5},
        "result_desc": "정원 바닥을 화려하게 장식합니다.",
        "rarity": "Rare",
        "effect": "furniture"
    },
    "특제 스테이크": {
        "ingredients": {"고기": 3, "소금": 1, "허브": 1},
        "result_desc": "육즙이 가득한 최고급 스테이크! (모든 쿨다운 초기화 / 호감도 +100)",
        "rarity": "Rare",
        "effect": "cooldown_reset",
        "value": 100
    },
    "해물 파스타": {
        "ingredients": {"밀가루": 2, "새우": 2, "오징어": 1},
        "result_desc": "바다의 향기가 느껴지는 파스타입니다. (낚시 쿨다운 초기화 / 호감도 +100)",
        "rarity": "Uncommon",
        "effect": "fishing_reset",
        "value": 100
    },
    "과일 탕후루": {
        "ingredients": {"설탕": 2, "딸기": 3},
        "result_desc": "바삭하고 달콤한 간식! (사냥 쿨다운 초기화 / 호감도 +300)",
        "rarity": "Common",
        "effect": "hunt_reset",
        "value": 300
    },
    "활력 포션": {
        "ingredients": {"약초": 5, "물": 1},
        "result_desc": "지친 몸에 활력을 불어넣습니다. (광질 쿨다운 초기화 / 호감도 +50)",
        "rarity": "Uncommon",
        "effect": "mining_reset",
        "value": 50
    },
    "황금 볶음밥": {
        "ingredients": {"쌀": 3, "계란": 2, "황금": 1},
        "result_desc": "황금처럼 빛나는 볶음밥입니다. (30만 젤리 획득 / 호감도 +2000)",
        "rarity": "Epic",
        "effect": "money_bag",
        "value": 2000,
        "money": 300000
    },
    "무지개 케이크": {
        "ingredients": {"밀가루": 5, "설탕": 5, "우유": 3, "무지개빛 정수": 1},
        "result_desc": "환상적인 맛이 나는 전설의 케이크! (모든 쿨다운 초기화 + 100만 젤리 / 호감도 +10000)",
        "rarity": "Legendary",
        "effect": "god_bless",
        "value": 10000,
        "money": 1000000
    },
    "한입초쌈": {
        "ingredients": {"허브": 2, "식초": 1},
        "result_desc": "숲에서 홀로 지내던 시절 즐겨 먹던 나물 쌈입니다. (건강해지는 맛! / 호감도 +300)",
        "rarity": "Uncommon",
        "effect": "affinity_boost",
        "value": 300
    },
    "크림 브륄레": {
        "ingredients": {"계란": 1, "설탕": 1, "크림": 1},
        "result_desc": "달콤하고 부드러운 디저트지만... 요미는 자극적인 걸 잘 못 먹나 봐요. (호감도 +50)",
        "rarity": "Rare",
        "effect": "affinity_boost",
        "value": 50
    },
    "딸기 케이크": {
        "ingredients": {"밀가루": 1, "설탕": 1, "딸기": 2, "크림": 1},
        "result_desc": "요정이 싫어하는 음식이 있다니?! 요미 입맛엔 안 맞나 봅니다. (호감도 +50)",
        "rarity": "Rare",
        "effect": "affinity_boost",
        "value": 50
    },
    "송편": {
        "ingredients": {"쌀": 2, "설탕": 1, "꿀": 1},
        "result_desc": "요미 입맛에 딱 맞는 적당한 단맛! 한 그릇 뚝딱! (호감도 +1500)",
        "rarity": "Rare",
        "effect": "affinity_boost",
        "value": 1500
    },
    "새콤비타F": {
        "ingredients": {"레몬": 2, "설탕": 1},
        "result_desc": "너무 셔서 얼굴이 찌푸려지지만 중독성 있는 맛! (사냥 쿨다운 초기화 / 호감도 +200)",
        "rarity": "Uncommon",
        "effect": "hunt_reset",
        "value": 200
    },
    "부쉬 드 노엘": {
        "ingredients": {"밀가루": 2, "초콜릿": 2, "크림": 1, "계란": 1},
        "result_desc": "사제장님 몰래 먹는 케이크가 제일 맛있죠! (호감도 +2000)",
        "rarity": "Epic",
        "effect": "affinity_boost",
        "value": 2000
    },
    "아몬드 로쉐": {
        "ingredients": {"초콜릿": 2, "아몬드": 2},
        "result_desc": "초콜릿보다 아몬드의 고소함이 더 좋대요. (호감도 +1000)",
        "rarity": "Rare",
        "effect": "affinity_boost",
        "value": 1000
    },
    "떡국": {
        "ingredients": {"쌀": 2, "물": 2, "고기": 1, "계란": 1},
        "result_desc": "따뜻한 국물이 일품! 마음까지 따뜻해져요. (모든 쿨다운 초기화 / 호감도 +500)",
        "rarity": "Epic",
        "effect": "cooldown_reset",
        "value": 500
    },
    "에심당 뿔사탕": {
        "ingredients": {"설탕": 3, "물": 1, "딸기": 1},
        "result_desc": "알록달록한 사탕이지만 요미 취향은 아닌가 봐요. (랜덤 효과 / 호감도 +100)",
        "rarity": "Rare",
        "effect": "random_effect",
        "value": 100
    }
}
PET_DATA = {
    "달토끼": {
        "type": "eco",
        "desc": "일정 시간마다 자동으로 젤리를 수확합니다.",
        "emoji": "🐰",
        "base_bonus": 0.05,
        "grade": "common",
        "combat": {
            "type": "heal",
            "rate": 0.1,
            "value": 0.05,            "msg": "🐰 달토끼가 당근을 건네 체력을 회복시켜줍니다!"
        }
    },
    "아기 슬라임": {
        "type": "eco",
        "desc": "젤리를 조금씩 흘리고 다닙니다.",
        "emoji": "💧",
        "base_bonus": 0.03,
        "grade": "common",
        "combat": {
            "type": "attack",
            "rate": 0.15,
            "value": 0.2,            "msg": "💧 아기 슬라임이 몸통 박치기를 합니다!"
        }
    },
    "돌멩이 정령": {
        "type": "defense",
        "desc": "단단한 몸으로 주인을 보호합니다.",
        "emoji": "🪨",
        "base_bonus": 0.05,
        "grade": "common",
        "combat": {
            "type": "defense",
            "rate": 0.2,
            "value": 0.3,            "msg": "🪨 돌멩이 정령이 앞을 막아섭니다!"
        }
    },
    "반짝이는 요정": {
        "type": "chance",
        "desc": "광질/낚시 성공 확률을 높여줍니다.",
        "emoji": "✨",
        "base_bonus": 0.05,
        "grade": "rare",
        "combat": {
            "type": "mana",
            "rate": 0.1,
            "value": 0.1,            "msg": "✨ 요정이 마법 가루를 뿌려 마력을 회복합니다!"
        }
    },
    "부엉이 파수꾼": {
        "type": "defense",
        "desc": "던전 탐험 시 주인을 지켜줍니다.",
        "emoji": "🦉",
        "base_bonus": 0.1,
        "grade": "rare",
        "combat": {
            "type": "dodge",
            "rate": 0.1,
            "value": 0,            "msg": "🦉 부엉이가 위험을 미리 알려 회피했습니다!"
        }
    },
    "불꽃 도마뱀": {
        "type": "attack",
        "desc": "작은 불꽃을 뿜어 공격을 돕습니다.",
        "emoji": "🦎",
        "base_bonus": 0.1,
        "grade": "rare",
        "combat": {
            "type": "attack",
            "rate": 0.2,
            "value": 0.5,            "msg": "🦎 불꽃 도마뱀이 화염을 내뿜습니다!"
        }
    },
    "전설의 피닉스": {
        "type": "resurrection",
        "desc": "쓰러졌을 때 한 번 부활시켜줍니다.",
        "emoji": "🔥",
        "base_bonus": 1.0,
        "grade": "legendary",
        "combat": {
            "type": "attack",
            "rate": 0.15,
            "value": 1.0,            "msg": "🔥 피닉스가 전장을 휩씁니다!"
        }
    },
    "달빛 드래곤": {
        "type": "all_stats",
        "desc": "모든 능력을 대폭 향상시킵니다.",
        "emoji": "🐲",
        "base_bonus": 0.2,
        "grade": "legendary",
        "combat": {
            "type": "attack",
            "rate": 0.25,
            "value": 1.5,            "msg": "🐲 달빛 드래곤이 용의 숨결을 내뿜습니다!"
        }
    },
    "다람쥐": {
        "type": "eco",
        "desc": "도토리를 모으듯 젤리를 부지런히 모읍니다.",
        "emoji": "🐿️",
        "base_bonus": 0.04,
        "grade": "common",
        "combat": {
            "type": "attack",
            "rate": 0.2,
            "value": 0.1,            "msg": "🐿️ 다람쥐가 도토리를 던져 공격합니다!"
        }
    },
    "병아리": {
        "type": "eco",
        "desc": "삐약삐약! 작지만 용감합니다.",
        "emoji": "🐥",
        "base_bonus": 0.02,
        "grade": "common",
        "combat": {
            "type": "attack",
            "rate": 0.1,
            "value": 0.15,            "msg": "🐥 병아리가 부리로 쪼아 공격합니다!"
        }
    },
    "늑대": {
        "type": "attack",
        "desc": "야생의 본능으로 적을 공격합니다.",
        "emoji": "🐺",
        "base_bonus": 0.08,
        "grade": "rare",
        "combat": {
            "type": "attack",
            "rate": 0.25,
            "value": 0.4,            "msg": "🐺 늑대가 날카로운 이빨로 물어뜯습니다!"
        }
    },
    "곰": {
        "type": "defense",
        "desc": "거대한 몸집으로 공격을 막아냅니다.",
        "emoji": "🐻",
        "base_bonus": 0.08,
        "grade": "rare",
        "combat": {
            "type": "defense",
            "rate": 0.25,
            "value": 0.4,            "msg": "🐻 곰이 앞발로 공격을 쳐냅니다!"
        }
    },
    "유니콘": {
        "type": "healing",
        "desc": "신성한 뿔로 상처를 치유합니다.",
        "emoji": "🦄",
        "base_bonus": 0.1,
        "grade": "epic",
        "combat": {
            "type": "heal",
            "rate": 0.15,
            "value": 0.15,            "msg": "🦄 유니콘의 뿔에서 치유의 빛이 뿜어져 나옵니다!"
        }
    },
    "그리핀": {
        "type": "attack",
        "desc": "하늘의 제왕, 그리핀입니다.",
        "emoji": "🦅",
        "base_bonus": 0.12,
        "grade": "epic",
        "combat": {
            "type": "attack",
            "rate": 0.2,
            "value": 0.8,            "msg": "🦅 그리핀이 하늘에서 급강하하여 공격합니다!"
        }
    },
    "구미호": {
        "type": "chance",
        "desc": "아홉 개의 꼬리를 가진 신비한 여우입니다.",
        "emoji": "🦊",
        "base_bonus": 0.15,
        "grade": "epic",
        "combat": {
            "type": "mana",
            "rate": 0.2,
            "value": 0.2,            "msg": "🦊 구미호가 여우구슬의 힘을 빌려 마력을 회복시킵니다!"
        }
    },
    "베히모스": {
        "type": "defense",
        "desc": "대지를 울리는 거대한 괴수입니다.",
        "emoji": "🐘",
        "base_bonus": 0.25,
        "grade": "legendary",
        "combat": {
            "type": "defense",
            "rate": 0.3,
            "value": 0.6,            "msg": "🐘 베히모스가 포효하며 충격을 상쇄합니다!"
        }
    },
    "레비아탄": {
        "type": "attack",
        "desc": "심해의 공포, 바다의 지배자입니다.",
        "emoji": "🌊",
        "base_bonus": 0.25,
        "grade": "legendary",
        "combat": {
            "type": "attack",
            "rate": 0.3,
            "value": 1.2,            "msg": "🌊 레비아탄이 거대한 해일을 일으킵니다!"
        }
    },
    "하늘 고래": {
        "type": "eco",
        "desc": "하늘을 유영하며 젤리 구름을 모읍니다.",
        "emoji": "🐋",
        "base_bonus": 0.15,
        "grade": "epic",
        "combat": {
            "type": "heal",
            "rate": 0.2,
            "value": 0.2,            "msg": "🐋 하늘 고래가 치유의 비를 내립니다!"
        }
    },
    "그림자 고양이": {
        "type": "chance",
        "desc": "어둠 속에서 행운을 물어옵니다.",
        "emoji": "🐈‍⬛",
        "base_bonus": 0.12,
        "grade": "epic",
        "combat": {
            "type": "dodge",
            "rate": 0.25,
            "value": 0,            "msg": "🐈‍⬛ 그림자 고양이가 적의 시야를 가립니다!"
        }
    },
    "수호의 정령": {
        "type": "defense",
        "desc": "절대적인 방어력으로 주인을 보호합니다.",
        "emoji": "🛡️",
        "base_bonus": 0.3,
        "grade": "legendary",
        "combat": {
            "type": "defense",
            "rate": 0.35,
            "value": 0.7,            "msg": "🛡️ 수호의 정령이 결계를 펼칩니다!"
        }
    }
}