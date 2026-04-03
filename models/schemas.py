"""
models/schemas.py — Todos os modelos Pydantic do Personal AI Mobile
"""
from __future__ import annotations
from typing import Any, Optional, List, Dict
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


def gen_id() -> str:
    return str(uuid.uuid4())


# ════════════════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════════════════
class Provider(str, Enum):
    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"
    genspark = "genspark"
    ollama = "ollama"

class AutonomyLevel(str, Enum):
    passive = "passive"
    balanced = "balanced"
    proactive = "proactive"

class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    dead_letter = "dead_letter"

class MemoryType(str, Enum):
    fact = "fact"
    preference = "preference"
    event = "event"
    person = "person"
    note = "note"
    context = "context"

class BluetoothDeviceType(str, Enum):
    speaker = "speaker"
    headphone = "headphone"
    tv = "tv"
    car_audio = "car_audio"
    multimedia = "multimedia"
    phone = "phone"
    unknown = "unknown"

class SyncOperation(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"


# ════════════════════════════════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════════════════════════════════
class ChatMessage(BaseModel):
    role: str
    content: str
    meta: Dict[str, Any] = {}

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    platform: str = "mobile"
    voice_response: bool = False
    provider: Optional[Provider] = None
    stream: bool = False

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    message_id: str
    provider_used: str
    tokens_used: int = 0
    audio_url: Optional[str] = None
    suggestions: List[str] = []
    memories_used: List[str] = []

class ConversationSummary(BaseModel):
    id: str
    title: Optional[str]
    platform: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


# ════════════════════════════════════════════════════════════════════════════
# MEMORY
# ════════════════════════════════════════════════════════════════════════════
class MemoryCreate(BaseModel):
    type: MemoryType
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: Optional[str] = None
    tags: List[str] = []
    expires_at: Optional[datetime] = None
    meta: Dict[str, Any] = {}

class MemoryItem(MemoryCreate):
    id: str
    created_at: datetime
    updated_at: datetime

class MemorySearchResult(BaseModel):
    id: str
    type: MemoryType
    content: str
    importance: float
    score: float
    tags: List[str] = []


# ════════════════════════════════════════════════════════════════════════════
# CALENDAR
# ════════════════════════════════════════════════════════════════════════════
class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    location: Optional[str] = None
    all_day: bool = False
    recurrence: Optional[str] = None
    reminder_min: int = 15
    platform: str = "local"
    external_id: Optional[str] = None
    meta: Dict[str, Any] = {}

class CalendarEvent(CalendarEventCreate):
    id: str
    status: str = "confirmed"
    created_at: datetime
    updated_at: datetime

class DailyAgenda(BaseModel):
    date: str
    events: List[CalendarEvent]
    summary: str = ""


# ════════════════════════════════════════════════════════════════════════════
# BLUETOOTH
# ════════════════════════════════════════════════════════════════════════════
class BluetoothDevice(BaseModel):
    mac_address: str
    name: Optional[str] = None
    device_type: BluetoothDeviceType = BluetoothDeviceType.unknown
    trusted: bool = False
    rssi: Optional[int] = None
    last_seen: Optional[datetime] = None
    meta: Dict[str, Any] = {}

class BluetoothScanResult(BaseModel):
    devices: List[BluetoothDevice]
    scan_duration: int
    total_found: int


# ════════════════════════════════════════════════════════════════════════════
# VOICE
# ════════════════════════════════════════════════════════════════════════════
class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: float = 1.0
    language: str = "pt-BR"
    backend: Optional[str] = None

class STTResult(BaseModel):
    text: str
    confidence: float
    language: str
    duration_ms: int

class VoiceCommandResult(BaseModel):
    raw_text: str
    intent: str
    entities: Dict[str, Any] = {}
    confidence: float
    action_taken: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# TELEPHONY
# ════════════════════════════════════════════════════════════════════════════
class CallRequest(BaseModel):
    number: str
    contact_name: Optional[str] = None
    via: str = "sip"   # sip | gsm | voip

class CallStatus(BaseModel):
    call_id: str
    number: str
    direction: str
    status: str
    duration_s: int = 0
    started_at: Optional[datetime] = None

class CallLog(BaseModel):
    id: str
    direction: str
    number: str
    contact_name: Optional[str] = None
    duration_s: int
    status: str
    started_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# JOBS
# ════════════════════════════════════════════════════════════════════════════
class JobCreate(BaseModel):
    type: str
    payload: Dict[str, Any] = {}
    priority: int = Field(default=5, ge=1, le=10)
    scheduled_at: Optional[datetime] = None
    depends_on: Optional[str] = None
    max_attempts: int = 3

class Job(JobCreate):
    id: str
    status: JobStatus = JobStatus.pending
    attempts: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# ROUTINES
# ════════════════════════════════════════════════════════════════════════════
class RoutineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    cron_expr: str
    actions: List[Dict[str, Any]] = []
    enabled: bool = True
    meta: Dict[str, Any] = {}

class Routine(RoutineCreate):
    id: str
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# GOALS / AUTONOMY
# ════════════════════════════════════════════════════════════════════════════
class GoalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    meta: Dict[str, Any] = {}

class Goal(GoalCreate):
    id: str
    status: str = "active"
    progress: float = 0.0
    created_at: datetime
    updated_at: datetime

class ProactiveSuggestion(BaseModel):
    id: str
    trigger: str
    suggestion: str
    action_type: str
    confidence: float
    context: Dict[str, Any] = {}


# ════════════════════════════════════════════════════════════════════════════
# SYSTEM STATUS
# ════════════════════════════════════════════════════════════════════════════
class ServiceStatus(BaseModel):
    name: str
    status: str        # running | stopped | error | degraded
    uptime_s: float = 0
    last_check: Optional[datetime] = None
    details: Dict[str, Any] = {}

class SystemStatus(BaseModel):
    app_version: str
    uptime_s: float
    online: bool
    autonomy_level: str
    services: List[ServiceStatus]
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_free_gb: float
    active_jobs: int
    pending_sync: int
    active_calls: int
    bluetooth_connected: int
    recorded_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# SELF-IMPROVEMENT
# ════════════════════════════════════════════════════════════════════════════
class ImprovementPatch(BaseModel):
    id: str
    title: str
    description: str
    patch_type: str     # feature | bugfix | optimization | security
    status: str         # proposed | testing | approved | applied | rejected
    file_path: Optional[str] = None
    generated_code: Optional[str] = None
    test_code: Optional[str] = None
    ai_provider: Optional[str] = None
    test_result: Optional[str] = None
    created_at: datetime
    applied_at: Optional[datetime] = None
    meta: Dict[str, Any] = {}

class MonitoringReport(BaseModel):
    period_hours: int
    metrics: Dict[str, Any]
    anomalies: List[Dict[str, Any]]
    suggestions: List[ImprovementPatch]
    health_score: float
    generated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# SYNC
# ════════════════════════════════════════════════════════════════════════════
class SyncItem(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    operation: SyncOperation
    payload: Dict[str, Any] = {}
    synced: bool = False
    retry_count: int = 0
    created_at: datetime

class SyncStatus(BaseModel):
    online: bool
    last_sync: Optional[datetime]
    pending_items: int
    synced_today: int
    errors: List[str] = []


# ════════════════════════════════════════════════════════════════════════════
# PLATFORMS (Alexa, Google, Spotify, Apps)
# ════════════════════════════════════════════════════════════════════════════
class AlexaRequest(BaseModel):
    version: str = "1.0"
    session: Dict[str, Any] = {}
    request: Dict[str, Any] = {}

class GoogleAssistantRequest(BaseModel):
    handler: Dict[str, Any] = {}
    intent: Dict[str, Any] = {}
    scene: Optional[Dict[str, Any]] = None

class SpotifyCommand(BaseModel):
    action: str   # play | pause | next | previous | search | volume
    query: Optional[str] = None
    volume: Optional[int] = None
    device_id: Optional[str] = None

class AppLaunchRequest(BaseModel):
    app_name: str
    platform: str = "android"   # android | ios | web
    deep_link: Optional[str] = None
    params: Dict[str, Any] = {}

class MediaControlRequest(BaseModel):
    action: str   # play | pause | stop | next | previous | seek | volume
    app: Optional[str] = None
    value: Optional[Any] = None


# ════════════════════════════════════════════════════════════════════════════
# CONTACTS
# ════════════════════════════════════════════════════════════════════════════
class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    platform: str = "local"
    external_id: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None
    meta: Dict[str, Any] = {}

class Contact(ContactCreate):
    id: str
    created_at: datetime
    updated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# GENERIC RESPONSE
# ════════════════════════════════════════════════════════════════════════════
class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None
    error: Optional[str] = None
