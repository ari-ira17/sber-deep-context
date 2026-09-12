from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

OCR_MIN_TEXT_LENGTH = 50


def preprocess_image(image: Image.Image) -> Image.Image:
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    return image.point(lambda pixel: 255 if pixel > 180 else 0)


def parse_png(path: str | Path) -> dict:
    with Image.open(Path(path)) as image:
        image = preprocess_image(image)
        text = pytesseract.image_to_string(image, lang="rus+eng", config="--psm 6").strip()
    return {
        "text": text,
        "ocr_used": True,
        "confidence": "normal" if len(text) >= OCR_MIN_TEXT_LENGTH else "LOW_CONFIDENCE",
    }
