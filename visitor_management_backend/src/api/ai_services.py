"""
Adapters for AI/ML integrations: Speech-to-Text (STT), Text-to-Speech (TTS), and OCR.

Switch between local open source models or external APIs by changing function implementation.
For production, set up API keys and cloud service configs as needed.
"""

import io
import os
from typing import Optional

# --- OCR ---
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

# --- Speech-To-Text ---
try:
    import speech_recognition as sr
except ImportError:
    sr = None

# --- Text-To-Speech ---
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


# PUBLIC_INTERFACE
def perform_ocr_on_image(file_bytes: bytes) -> dict:
    """
    Run OCR on the provided image file bytes.

    Args:
        file_bytes (bytes): Image file data.

    Returns:
        dict: Extracted fields {field_name: value}
    """
    if not pytesseract or not Image:
        return {"error": "OCR library not installed"}
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        # Dummy logic: split to lines & pick "full_name" and "id_number"
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return {
            "ocr_text": text,
            "lines": lines,
        }
    except Exception as ex:
        return {"error": str(ex)}


# PUBLIC_INTERFACE
def perform_speech_to_text(audio_bytes: bytes, language: str = "en-US") -> dict:
    """
    Convert audio bytes (wav, mp3, etc.) to text using STT.

    Args:
        audio_bytes (bytes): Audio file data.
        language (str): Language code ("en-US", etc.)

    Returns:
        dict: {'transcript': ..., 'language': ...}
    """
    if not sr:
        return {"error": "SpeechRecognition not installed"}
    # Use SpeechRecognition with a default recognizer and Google Web API for demo (no API key required for basic usage)
    rec = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = rec.record(source)
            transcript = rec.recognize_google(audio, language=language)
            return {"transcript": transcript, "language": language}
    except Exception as ex:
        return {"error": str(ex)}


# PUBLIC_INTERFACE
def perform_text_to_speech(text: str, language: str = "en") -> Optional[bytes]:
    """
    Convert text to speech audio bytes (wav) using TTS.

    Args:
        text (str): Input text to speak.
        language (str): Language code ("en", ...)

    Returns:
        bytes: WAV audio, or None if error.
    """
    if not pyttsx3:
        return None
    try:
        engine = pyttsx3.init()
        # Optionally, set language here if needed
        # For demo, English is fine
        # pyttsx3 does not have native support to write to BytesIO,
        # so this workaround: save as wav file temporarily
        tmpfile = "/tmp/tts_speak.wav"
        engine.save_to_file(text, tmpfile)
        engine.runAndWait()
        with open(tmpfile, "rb") as f:
            audio_data = f.read()
        os.remove(tmpfile)
        return audio_data
    except Exception:
        return None

