from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from starlette.status import HTTP_400_BAD_REQUEST
import io
import datetime

from .database import get_db
from .models import Visitor, VisitLog, Host, AdminUser

from .ai_services import (
    perform_ocr_on_image,
    perform_speech_to_text,
    perform_text_to_speech,
)

app = FastAPI(
    title="Visitor Management Kiosk Backend",
    description="API for Visitor Kiosk (Check-in, Speech, OCR, Notifications, Admin) with conversational logic and PostgreSQL integration.",
    version="1.0.0",
    openapi_tags=[
        {"name": "visitor", "description": "Visitor check-in and management"},
        {"name": "ocr", "description": "ID OCR upload"},
        {"name": "speech", "description": "STT/TTS APIs"},
        {"name": "notifications", "description": "Notification triggers to hosts"},
        {"name": "admin", "description": "Admin management & dashboard"},
        {"name": "validation", "description": "Real-time field validation"},
    ],
)

import os
from dotenv import load_dotenv

load_dotenv()

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],  # Restrict to frontend origin for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Pydantic Schemas --------------------

class VisitorCheckinStepRequest(BaseModel):
    """Represents one Q&A step in conversational visitor check-in."""
    conversation_state: Dict[str, str] = Field(..., description="Collected data so far (may be partial)")
    user_input: str = Field(..., description="Current raw input (spoken or typed)")
    input_mode: str = Field(..., description="'voice' or 'text'")


class VisitorCheckinStepResponse(BaseModel):
    """API: System prompt and next expected data key."""
    next_prompt: str
    next_field: Optional[str] = None
    conversation_state: Dict[str, str]
    is_complete: bool = False
    errors: Optional[List[str]] = None
    advice: Optional[str] = None


class VisitorCreatePayload(BaseModel):
    full_name: str = Field(..., example="Alice Smith")
    email: Optional[EmailStr]
    phone: Optional[str]
    id_number: Optional[str]


class VisitorOut(BaseModel):
    id: int
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    id_number: Optional[str]
    created_at: datetime.datetime

    class Config:
        orm_mode = True


class HostOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str]
    department: Optional[str]

    class Config:
        orm_mode = True


class VisitLogOut(BaseModel):
    id: int
    visitor: VisitorOut
    host: HostOut
    purpose: Optional[str]
    check_in_time: datetime.datetime
    check_out_time: Optional[datetime.datetime]
    status: str

    class Config:
        orm_mode = True


class AdminUserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        orm_mode = True

class FieldValidationRequest(BaseModel):
    field: str = Field(..., description="'email', 'phone', or other field name to validate")
    value: str


class FieldValidationResult(BaseModel):
    field: str
    value: str
    is_valid: bool
    errors: Optional[List[str]] = None

# -------------------- Health Check --------------------

# PUBLIC_INTERFACE
@app.get("/", tags=["admin"])
def health_check():
    """
    Health check endpoint.
    ---
    Returns {"message": "Healthy"} if API is up.
    """
    return {"message": "Healthy"}

# -------------------- Conversational Visitor Check-in APIs --------------------

# PUBLIC_INTERFACE
@app.post("/api/visitor/checkin-step", response_model=VisitorCheckinStepResponse, tags=["visitor"])
def visitor_checkin_step(payload: VisitorCheckinStepRequest):
    """
    Conversational visitor check-in step.
    Receives user input and partial conversation state,
    returns next prompt, next expected field, and updated state.
    """
    expected_fields_order = [
        ("full_name", "What is your full name?"),
        ("email",    "What is your email address? (You may skip)"),
        ("phone",    "And your phone number? (optional)"),
        ("id_number", "Do you have an ID or passport number to provide? (optional)"),
        ("host_email", "Who are you visiting today? Please provide their email."),
        ("purpose",   "What is the purpose of your visit?"),
    ]

    state = payload.conversation_state.copy()
    errors = []
    next_prompt = None
    next_field = None
    is_complete = False

    # Decision logic: Walk through fields, find next
    for field, prompt in expected_fields_order:
        if not state.get(field):
            next_prompt = prompt
            next_field = field
            break

    # Dummy validation and field value assignment
    raw_input = payload.user_input.strip()
    if next_field and raw_input:
        state[next_field] = raw_input

        # Simple validations example
        if next_field == "email":
            if "@" not in raw_input:
                errors.append("Invalid email format.")
        if next_field == "host_email":
            if "@" not in raw_input:
                errors.append("Please provide a valid email for the host.")

        # Now check again what's next after assignment
        for field, prompt in expected_fields_order:
            if not state.get(field):
                next_prompt = prompt
                next_field = field
                break
        else:
            is_complete = True
            next_prompt = "Thank you, your check-in data is almost complete. Please scan your ID, if required."

    return VisitorCheckinStepResponse(
        next_prompt=next_prompt,
        next_field=next_field,
        conversation_state=state,
        is_complete=is_complete,
        errors=errors if errors else None
    )


# PUBLIC_INTERFACE
@app.post("/api/visitor/checkin-finalize", response_model=VisitLogOut, tags=["visitor"])
def visitor_checkin_finalize(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Finalizes visitor check-in.
    Expects all fields in payload.
    Creates (or retrieves) Visitor, Host, and VisitLog.
    Returns complete visit log.
    """
    try:
        full_name = payload["full_name"]
        email = payload.get("email")
        phone = payload.get("phone")
        id_number = payload.get("id_number")
        purpose = payload.get("purpose")
        host_email = payload.get("host_email")
    except Exception:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Missing required check-in fields.")

    # Get or create Visitor
    visitor = db.query(Visitor).filter_by(full_name=full_name, email=email).first()
    if not visitor:
        visitor = Visitor(full_name=full_name, email=email, phone=phone, id_number=id_number)
        db.add(visitor)
        db.commit()
        db.refresh(visitor)
    # Get or create Host
    host = db.query(Host).filter_by(email=host_email).first()
    if not host:
        host = Host(full_name=host_email.split("@")[0], email=host_email)
        db.add(host)
        db.commit()
        db.refresh(host)
    # Create new VisitLog
    visit = VisitLog(
        visitor_id=visitor.id,
        host_id=host.id,
        purpose=purpose,
        status="checked_in"
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return VisitLogOut(
        id=visit.id,
        visitor=visitor,
        host=host,
        purpose=visit.purpose,
        check_in_time=visit.check_in_time,
        check_out_time=visit.check_out_time,
        status=visit.status,
    )

# -------------------- OCR: ID Upload --------------------

# PUBLIC_INTERFACE
@app.post("/api/ocr/upload-id", tags=["ocr"])
async def upload_id_ocr(file: UploadFile = File(...)):
    """
    Accepts an ID card/passport image.
    Integrates with Tesseract OCR (if available).
    Returns extracted fields (OCR output or fallback).
    """
    image_bytes = await file.read()
    ocr_result = perform_ocr_on_image(image_bytes)
    if "error" in ocr_result:
        ext_fields = {
            "full_name": "Demo Person",
            "id_number": "ID123456789",
            "dob": "1990-01-01"
        }
        return JSONResponse(
            {"status": "fallback", "ocr_fields": ext_fields, "filename": file.filename, "message": ocr_result["error"]}
        )
    else:
        return {"status": "success", "ocr_fields": ocr_result, "filename": file.filename}

# -------------------- Speech AI (STT & TTS) --------------------

class SpeechRequest(BaseModel):
    audio_data: bytes = Field(..., description="Audio file bytes (base64-encoded or binary, but see note)")
    language: Optional[str] = Field("en", description="Language code for STT/TTS")

class TextToSpeechRequest(BaseModel):
    text: str = Field(..., description="Text to convert to speech")
    language: Optional[str] = Field("en", description="Language code for TTS")

# PUBLIC_INTERFACE
@app.post("/api/speech/stt", tags=["speech"])
async def speech_to_text_stub(file: UploadFile = File(...), language: Optional[str] = Form("en-US")):
    """
    Accepts audio file; returns speech-to-text transcript.
    """
    audio_bytes = await file.read()
    stt_result = perform_speech_to_text(audio_bytes, language=language or "en-US")
    if "error" in stt_result:
        transcript = "This is a dummy transcript of the audio (could not perform real STT: %s)" % stt_result["error"]
        return {"transcript": transcript, "language": language, "filename": file.filename}
    return {**stt_result, "filename": file.filename}

# PUBLIC_INTERFACE
@app.post("/api/speech/tts", tags=["speech"])
async def text_to_speech_stub(request: TextToSpeechRequest):
    """
    Accepts text and returns speech audio stream (TTS).
    Responds with real audio if TTS available, else dummy wav.
    """
    wav_data = perform_text_to_speech(request.text, request.language or "en")
    if not wav_data:
        # Fallback: return demo WAV header w/silence
        wav_data = (
            b'RIFF$\x00\x00\x00WAVEfmt '
            b'\x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00'
            b'\x02\x00\x10\x00data\x00\x00\x00\x00'
        )
    return StreamingResponse(io.BytesIO(wav_data), media_type="audio/wav")

# -------------------- Notifications --------------------

# PUBLIC_INTERFACE
@app.post("/api/notifications/notify-host", tags=["notifications"])
def notify_host(body: Dict[str, Any] = Body(...)):
    """
    API to trigger host notifications (stub, to integrate with mail/SMS/Slack).
    Expects at minimum: host_email and visitor info.
    """
    # In reality: call mail, SMS, push service here
    host_email = body.get("host_email")
    visitor_name = body.get("visitor_name")
    if not host_email or not visitor_name:
        raise HTTPException(400, "host_email and visitor_name required")
    # Actual notification sending logic goes here
    return {"status": "sent", "host_email": host_email, "visitor_name": visitor_name}

# -------------------- Admin Dashboard Endpoints --------------------

# PUBLIC_INTERFACE
@app.get("/api/admin/visitors", response_model=List[VisitorOut], tags=["admin"])
def get_visitors(skip: int = 0, limit: int = 25, db: Session = Depends(get_db)):
    """
    List all visitors (paginated).
    """
    objs = db.query(Visitor).offset(skip).limit(limit).all()
    return objs

# PUBLIC_INTERFACE
@app.get("/api/admin/visitlogs", response_model=List[VisitLogOut], tags=["admin"])
def get_visitlogs(skip: int = 0, limit: int = 25, db: Session = Depends(get_db)):
    """
    List all visit logs (most recent first, paginated).
    """
    logs = (db.query(VisitLog)
            .order_by(VisitLog.check_in_time.desc())
            .offset(skip)
            .limit(limit)
            .all())
    return [
        VisitLogOut(
            id=log.id,
            visitor=log.visitor,
            host=log.host,
            purpose=log.purpose,
            check_in_time=log.check_in_time,
            check_out_time=log.check_out_time,
            status=log.status,
        ) for log in logs
    ]

# PUBLIC_INTERFACE
@app.get("/api/admin/hosts", response_model=List[HostOut], tags=["admin"])
def get_hosts(skip: int = 0, limit: int = 25, db: Session = Depends(get_db)):
    """
    List all hosts/employees.
    """
    return db.query(Host).offset(skip).limit(limit).all()

# PUBLIC_INTERFACE
@app.get("/api/admin/users", response_model=List[AdminUserOut], tags=["admin"])
def get_admin_users(skip: int = 0, limit: int = 25, db: Session = Depends(get_db)):
    """
    List all admin users (for dashboard).
    """
    return db.query(AdminUser).offset(skip).limit(limit).all()

# -------------------- Real-time Field Validation --------------------

# PUBLIC_INTERFACE
@app.post("/api/validation/validate-field", response_model=FieldValidationResult, tags=["validation"])
def validate_field(payload: FieldValidationRequest):
    """
    Real-time field validation API for frontend forms.
    Returns validity and errors, if any.
    """
    field = payload.field
    value = payload.value
    is_valid = True
    errors = []

    # Example: validation logic (email/phone/id)
    if field == "email":
        if "@" not in value:
            is_valid = False
            errors.append("Invalid email format.")
    elif field == "phone":
        if not value.isdigit() or not (7 <= len(value) <= 15):
            is_valid = False
            errors.append("Invalid phone number; must be 7-15 digits.")
    elif field == "id_number":
        if len(value) < 3:
            is_valid = False
            errors.append("ID must be at least 3 characters.")

    return FieldValidationResult(field=field, value=value, is_valid=is_valid, errors=errors or None)

# --------------- WebSocket Usage Guide in API Docs -------------

@app.get("/api/docs/websocket-usage", tags=["admin"])
def websocket_usage():
    """
    Endpoint for frontend devs to see how to use real-time features.
    (No live WS in this backend, but doc stub is here for OpenAPI.)
    """
    return {
        "websocket_url": "/ws/{purpose}",
        "note": "This backend delivers real-time validation/query via HTTP endpoints, not by WebSocket."
    }
