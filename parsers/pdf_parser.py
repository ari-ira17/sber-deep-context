from pathlib import Path
import io
import fitz
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import pytesseract

OCR_MIN_TEXT_LENGTH = 50


def _preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    return image.point(lambda pixel: 255 if pixel > 180 else 0)


def _ocr_page(page, dpi: int = 300) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    image = _preprocess(image)
    return pytesseract.image_to_string(image, lang="rus+eng", config="--psm 6").strip()


def parse_pdf(path: str | Path) -> dict:
    document = fitz.open(Path(path))
    try:
        normal = "\n\n".join(p.get_text("text").strip() for p in document if p.get_text("text").strip()).strip()
        if len(normal) >= OCR_MIN_TEXT_LENGTH:
            return {"text": normal, "ocr_used": False, "confidence": "normal"}
        ocr = "\n\n".join(t for t in (_ocr_page(p) for p in document) if t).strip()
        return {"text": ocr, "ocr_used": True,
                "confidence": "normal" if len(ocr) >= OCR_MIN_TEXT_LENGTH else "LOW_CONFIDENCE"}
    finally:
        document.close()
