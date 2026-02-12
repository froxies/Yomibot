
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pilmoji import Pilmoji
from pilmoji.source import AppleEmojiSource
import io
import os

FONT_PATH = "fonts/Pretendard-Bold.ttf"
EMOJI_FONT_PATH = "fonts/seguiemj.ttf"

def create_rounded_rectangle(size, radius, color):

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=color)
    return img

def create_circular_mask(size):

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    return mask

def _generate_profile_image_sync(user_name: str, avatar_bytes: bytes, level: int, xp: int, xp_max: int, balance: int, rank_text: str = "Common"):


    width, height = 800, 450

    background_color = (30, 33, 36)
    card_color = (40, 43, 48)
    text_color = (255, 255, 255)
    highlight_color = (255, 215, 0)
    base = Image.new("RGBA", (width, height), background_color)
    draw = ImageDraw.Draw(base)

    card_bg = create_rounded_rectangle((760, 410), 20, card_color)
    base.paste(card_bg, (20, 20), card_bg)

    try:
        font_large = ImageFont.truetype(FONT_PATH, 40)
        font_medium = ImageFont.truetype(FONT_PATH, 30)
        font_small = ImageFont.truetype(FONT_PATH, 20)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    try:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((150, 150))

        mask = create_circular_mask((150, 150))
        avatar_masked = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
        avatar_masked.paste(avatar, (0, 0), mask)

        draw.ellipse((45, 45, 205, 205), outline=highlight_color, width=5)
        base.paste(avatar_masked, (50, 50), avatar_masked)

    except Exception as e:
        print(f"Avatar Load Error: {e}")
        draw.ellipse((50, 50, 200, 200), fill=(100, 100, 100))
    with Pilmoji(base) as pilmoji:
        pilmoji.text((230, 60), user_name, font=font_large, fill=text_color, emoji_position_offset=(0, 3))

        pilmoji.text((230, 110), f"Rank: {rank_text}", font=font_medium, fill=(200, 200, 200), emoji_position_offset=(0, 3))

        draw.rounded_rectangle((650, 50, 750, 100), radius=10, fill=highlight_color)
        pilmoji.text((665, 60), f"Lv.{level}", font=font_medium, fill=(0, 0, 0), emoji_position_offset=(0, 3))

        bar_x, bar_y = 230, 160
        bar_w, bar_h = 520, 30

        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=15, fill=(20, 20, 20))

        if xp_max > 0:
            progress = min(1.0, xp / xp_max)
            fill_w = int(bar_w * progress)
            if fill_w > 0:
                draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=15, fill=(0, 255, 100))

        xp_text = f"{xp} / {xp_max} XP"
        text_bbox = draw.textbbox((0, 0), xp_text, font=font_small)
        text_w = text_bbox[2] - text_bbox[0]
        pilmoji.text((bar_x + (bar_w - text_w) // 2, bar_y + 5), xp_text, font=font_small, fill=(255, 255, 255), emoji_position_offset=(0, 3))

        pilmoji.text((50, 250), "💰 보유 자산", font=font_medium, fill=highlight_color, emoji_position_offset=(0, 3))
        pilmoji.text((50, 290), f"{balance:,} 젤리", font=font_large, fill=text_color, emoji_position_offset=(0, 3))

        pilmoji.text((400, 250), "📅 가입일", font=font_medium, fill=highlight_color, emoji_position_offset=(0, 3))
        pilmoji.text((400, 290), "2024-01-01", font=font_medium, fill=text_color, emoji_position_offset=(0, 3))
        draw.line((50, 380, 750, 380), fill=(100, 100, 100), width=2)
        pilmoji.text((50, 400), "Yomi Bot Economy System", font=font_small, fill=(150, 150, 150), emoji_position_offset=(0, 3))

    buffer = io.BytesIO()
    base.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

async def generate_profile_image(user_name: str, avatar_bytes: bytes, level: int, xp: int, xp_max: int, balance: int, rank_text: str = "Common"):

    return await asyncio.to_thread(
        _generate_profile_image_sync,
        user_name, avatar_bytes, level, xp, xp_max, balance, rank_text
    )