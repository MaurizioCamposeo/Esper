"""Produce searchable text from a photo or a scanned image."""

from __future__ import annotations

import csv
import io
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from esper.config import RUNTIME_DIR

if TYPE_CHECKING:
    from PIL import Image

CAPTION_MODEL = "florence-community/Florence-2-base-ft"
CAPTION_REVISION = "0b03b6f15a4a211370fb204aee4e7dd48887ea37"
OCR_LANGUAGE = "ita+eng"
OCR_LINE_CONFIDENCE = 70
OCR_WORD_CONFIDENCE = 45
_TSV_FIELDS = ("page_num", "block_num", "par_num", "line_num")


class ImageExtractionError(ValueError):
    """An image could not be read, transcribed or described."""


def read_image(path: Path) -> Image.Image:
    """Read a bounded, correctly oriented RGB image for both engines."""
    from PIL import Image, ImageOps

    try:
        with Image.open(path, formats=("JPEG", "PNG")) as image:
            if image.width * image.height > 64_000_000:
                raise ImageExtractionError("L’immagine supera il limite di 64 megapixel.")
            image = ImageOps.exif_transpose(image)
            image.thumbnail((3600, 3600))
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ImageExtractionError("Impossibile leggere l’immagine JPEG o PNG.") from exc


def _legible_line(words: list[tuple[str, float]]) -> bool:
    confident = [
        "".join(char for char in word if char.isalnum())
        for word, confidence in words if confidence >= OCR_LINE_CONFIDENCE
    ]
    confident = [word for word in confident if word]
    # Isolated two-letter shapes are common OCR noise in photos. Short codes
    # and numbers can still qualify without other words on the same line.
    return len(confident) >= 2 or any(
        len(word) >= 3 or (len(word) == 2 and any(char.isdigit() for char in word))
        for word in confident
    )


def ocr_text(tsv: str) -> str:
    """Keep legible lines, including a single confident serial number."""
    rows = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    if not set((*_TSV_FIELDS, "level", "text", "conf")).issubset(rows.fieldnames or ()):
        raise ImageExtractionError("Tesseract ha restituito un risultato OCR non valido.")
    lines = {}
    for row in rows:
        if row["level"] != "5" or not row["text"]:
            continue
        try:
            confidence = float(row["conf"])
        except (ValueError, TypeError) as exc:
            raise ImageExtractionError("Tesseract ha restituito un punteggio OCR non valido.") from exc
        if confidence >= OCR_WORD_CONFIDENCE and row["text"].strip():
            line = tuple(row[field] for field in _TSV_FIELDS)
            lines.setdefault(line, []).append((row["text"].strip(), confidence))
    return "\n".join(
        " ".join(word for word, _ in words)
        for words in lines.values()
        if _legible_line(words)
    )


def transcribe_image(image: Image.Image) -> str:
    """Run sparse-text OCR and distinguish an empty result from an engine error."""
    runtime = RUNTIME_DIR / "tesseract"
    executable = runtime / "bin" / "tesseract"
    command = ["tesseract", "stdin", "stdout", "-l", OCR_LANGUAGE, "--psm", "11"]
    if executable.is_file():
        command[0] = str(executable)
        command.extend(["--tessdata-dir", str(runtime / "tessdata")])
    command.append("tsv")

    data = io.BytesIO()
    image.save(data, format="PNG")
    try:
        result = subprocess.run(
            command,
            input=data.getvalue(), capture_output=True, timeout=45, check=False,
        )
    except FileNotFoundError as exc:
        raise ImageExtractionError("Per indicizzare le immagini, installa Tesseract e le lingue ita e eng.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ImageExtractionError("Tempo massimo superato durante il riconoscimento del testo.") from exc
    except OSError as exc:
        raise ImageExtractionError("Impossibile avviare Tesseract.") from exc
    stderr = result.stderr.decode("utf-8", errors="replace")
    if "Failed loading language" in stderr:
        raise ImageExtractionError("Per il riconoscimento del testo, installa i dati Tesseract per ita e eng.")
    if result.returncode:
        raise ImageExtractionError(f"Riconoscimento del testo non riuscito (Tesseract: {result.returncode}).")
    return ocr_text(result.stdout.decode("utf-8"))


@lru_cache(maxsize=1)
def _caption_model():
    """Load the pinned CPU captioner once, using only cached weights."""
    from transformers import Florence2ForConditionalGeneration, Florence2Processor

    bundled = RUNTIME_DIR / "hub" / ("models--" + CAPTION_MODEL.replace("/", "--")) / "snapshots" / CAPTION_REVISION
    source = str(bundled) if bundled.is_dir() else CAPTION_MODEL
    try:
        processor = Florence2Processor.from_pretrained(source, revision=CAPTION_REVISION, local_files_only=True)
        # The checkpoint is FP16. Use FP32 for inference on CPUs that emulate FP16.
        model = Florence2ForConditionalGeneration.from_pretrained(
            source, revision=CAPTION_REVISION, local_files_only=True, dtype="float32",
        )
    except OSError as exc:
        raise ImageExtractionError(
            "Il modello locale Florence-2 non è disponibile. Scarica i pesi come indicato in USAGE.md."
        ) from exc
    return processor, model.eval()


def describe_image(image: Image.Image) -> str:
    """Describe the image with the model’s paragraph-level captioning task."""
    import torch

    processor, model = _caption_model()
    task = "<MORE_DETAILED_CAPTION>"
    inputs = processor(text=task, images=image, return_tensors="pt")
    with torch.inference_mode():
        output = model.generate(**inputs, do_sample=False, num_beams=3, max_new_tokens=192, no_repeat_ngram_size=3)
    description = processor.decode(output[0], skip_special_tokens=True).strip()
    if not description:
        raise ImageExtractionError("Il modello non ha prodotto una descrizione dell’immagine.")
    return description
