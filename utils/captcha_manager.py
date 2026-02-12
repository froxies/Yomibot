import os
import random
import string
import io
from captcha.image import ImageCaptcha
def generate_random_text(length=5):
    letters = string.ascii_uppercase + string.digits
    ambiguous = "0O1Il"
    allowed = [c for c in letters if c not in ambiguous]
    return ''.join(random.choice(allowed) for i in range(length))
def generate_captcha_image(text: str) -> io.BytesIO:
    image = ImageCaptcha(width=280, height=90)
    data = image.generate(text)
    return data