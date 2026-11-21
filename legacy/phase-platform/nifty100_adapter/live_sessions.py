"""Live Session Integration for SI-Trader Platform.

BRD Section 28: Live session management using curriculum module IDs.
Live sessions for an uploaded curriculum use module ID `curriculum:<id>`.
Reuses the module live-session feature and resolves the curriculum's trainer.
"""
from __future__ import annotations


from enum import Enum
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path


class LiveSessionStatus(Enum):
    """Status of a live session."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SessionType(Enum):
    """Type of live session."""
    CURRICULUM_LIVE = "curriculum_live"
    TRAINER_Q_AND_A = "trainer_q_and_a"
    STRATEGY_DEMO = "strategy_demo"
    WEEKLY_REVIEW = "weekly_review"
    QUIZ_SESSION = "quiz_session"


class CurriculumModule:
    """A curriculum module with a live session ID."""
    def __init__(self, id: str, title: str, description: str,
                 trainer_id: str, session_type: SessionType = SessionType.CURRICULUM_LIVE,
                 max_participants: int = 100, scheduled_at: Optional[datetime] = None,
                 duration_minutes: int = 60, resources: Optional[List[str]] = None,
                 notes: str = ""):
        self.id = id  # Format: "curriculum:<module_id>"
        self.title = title
        self.description = description
        self.trainer_id = trainer_id
        self.session_type = session_type
        self.max_participants = max_participants
        self.scheduled_at = scheduled_at or datetime.now()
        self.enrolled_participants = 0
        self.started_at = None
        self.completed_at = None
        self.duration_minutes = duration_minutes
        self.recording_url = None
        self.resources = resources or []
        self.status = LiveSessionStatus.SCHEDULED
        self.notes = notes


class LiveSession:
    """A live session instance."""
    def __init__(self, id: str, curriculum_module_id: str, title: str,
                 description: str, trainer_id: str, session_type: SessionType,
                 max_participants: int, scheduled_at: datetime,
                 status: LiveSessionStatus = LiveSessionStatus.SCHEDULED,
                 started_at: Optional[datetime] = None,
                 completed_at: Optional[datetime] = None,
                 recording_url: Optional[str] = None):
        self.id = id
        self.curriculum_module_id = curriculum_module_id
        self.title = title
        self.description = description
        self.trainer_id = trainer_id
        self.session_type = session_type
        self.max_participants = max_participants
        self.enrolled_participants = 0
        self.scheduled_at = scheduled_at
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.recording_url = recording_url
        self.chat_log: List[Dict] = []
        self.poll_results: Optional[Dict] = None


# Live session data storage
LIVE_SESSIONS_DIR = Path(__file__).parent.parent / "live_session_data"
LIVE_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_INDEX_FILE = LIVE_SESSIONS_DIR / "sessions_index.json"
MODULES_INDEX_FILE = LIVE_SESSIONS_DIR / "modules_index.json"


def _load_sessions_index() -> Dict:
    """Load the live sessions index."""
    if SESSIONS_INDEX_FILE.exists():
        try:
            with open(SESSIONS_INDEX_FILE, 'r') as f:
                data = json.load(f)
                # Ensure proper structure
                if "sessions" not in data:
                    data["sessions"] = {}
                if "modules" not in data:
                    data["modules"] = {}
                return data
        except (json.JSONDecodeError, IOError):
            pass
    # Return proper structure
    return {"sessions": {}, "modules": {}}


def _save_sessions_index(index: Dict):
    """Save the live sessions index."""
    # Ensure proper structure
    if "sessions" not in index:
        index["sessions"] = {}
    if "modules" not in index:
        index["modules"] = {}
    with open(SESSIONS_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)


def _load_modules_index() -> Dict:
    """Load the curriculum modules index."""
    if MODULES_INDEX_FILE.exists():
        try:
            with open(MODULES_INDEX_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"modules": {}}
    return {"modules": {}}


def _save_modules_index(index: Dict):
    """Save the curriculum modules index."""
    with open(MODULES_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)


def create_curriculum_module(module_id: str, title: str, description: str,
                            trainer_id: str, session_type: SessionType = SessionType.CURRICULUM_LIVE,
                            max_participants: int = 100, scheduled_at: Optional[datetime] = None,
                            duration_minutes: int = 60, resources: Optional[List[str]] = None,
                            notes: str = "") -> CurriculumModule:
    """Create a new curriculum module with live session ID."""
    # Format module ID as curriculum:<module_id>
    full_module_id = f"curriculum:{module_id}"
    
    module = CurriculumModule(
        id=full_module_id,
        title=title,
        description=description,
        trainer_id=trainer_id,
        session_type=session_type,
        max_participants=max_participants,
        scheduled_at=scheduled_at or datetime.now(),
        duration_minutes=duration_minutes,
        resources=resources or [],
        notes=notes,
    )
    
    # Update indexes
    modules_index = _load_modules_index()
    modules_index["modules"][full_module_id] = {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "trainer_id": module.trainer_id,
        "session_type": module.session_type.value,
        "max_participants": module.max_participants,
        "scheduled_at": module.scheduled_at.isoformat(),
        "enrolled_participants": module.enrolled_participants,
        "status": module.status.value,
        "duration_minutes": module.duration_minutes,
        "resources": module.resources,
        "notes": module.notes,
    }
    
    # Also create an empty live session template
    sessions_index = _load_sessions_index()
    session_id = hashlib.sha256(f"{full_module_id}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    
    sessions_index["sessions"][session_id] = {
        "id": session_id,
        "curriculum_module_id": full_module_id,
        "title": module.title,
        "description": module.description,
        "trainer_id": module.trainer_id,
        "session_type": module.session_type.value,
        "max_participants": module.max_participants,
        "enrolled_participants": 0,
        "scheduled_at": module.scheduled_at.isoformat(),
        "status": LiveSessionStatus.SCHEDULED.value,
    }
    
    _save_modules_index(modules_index)
    _save_sessions_index(sessions_index)
    
    return module


def get_curriculum_module(module_id: str) -> Optional[CurriculumModule]:
    """Get a curriculum module by its ID (format: curriculum:<id>)."""
    modules_index = _load_modules_index()
    
    if module_id not in modules_index["modules"]:
        return None
    
    mdata = modules_index["modules"][module_id]
    return CurriculumModule(
        id=mdata["id"],
        title=mdata["title"],
        description=mdata["description"],
        trainer_id=mdata["trainer_id"],
        session_type=SessionType(mdata["session_type"]),
        max_participants=mdata["max_participants"],
        scheduled_at=datetime.fromisoformat(mdata["scheduled_at"]) if mdata.get("scheduled_at") else datetime.now(),
        duration_minutes=mdata.get("duration_minutes", 60),
        resources=mdata.get("resources", []),
        notes=mdata.get("notes", ""),
    )


def list_curriculum_modules() -> List[CurriculumModule]:
    """List all curriculum modules."""
    modules_index = _load_modules_index()
    
    modules = []
    for mid, mdata in modules_index["modules"].items():
        modules.append(get_curriculum_module(mid))
    return [m for m in modules if m is not None]


def start_live_session(session_id: str) -> Optional[LiveSession]:
    """Start a live session (transition from SCHEDULED to IN_PROGRESS)."""
    sessions_index = _load_sessions_index()
    
    if session_id not in sessions_index["sessions"]:
        return None
    
    session_data = sessions_index["sessions"][session_id]
    session_data["status"] = LiveSessionStatus.IN_PROGRESS.value
    session_data["started_at"] = datetime.now().isoformat()
    
    # Create LiveSession object
    session = LiveSession(
        id=session_id,
        curriculum_module_id=session_data["curriculum_module_id"],
        title=session_data["title"],
        description=session_data["description"],
        trainer_id=session_data["trainer_id"],
        session_type=SessionType(session_data["session_type"]),
        max_participants=session_data["max_participants"],
        enrolled_participants=session_data.get("enrolled_participants", 0),
        scheduled_at=datetime.fromisoformat(session_data["scheduled_at"]),
        status=LiveSessionStatus.IN_PROGRESS,
        started_at=datetime.now(),
    )
    
    _save_sessions_index(sessions_index)
    return session


def complete_live_session(session_id: str, recording_url: Optional[str] = None) -> Optional[LiveSession]:
    """Complete a live session (transition to COMPLETED)."""
    sessions_index = _load_sessions_index()
    
    if session_id not in sessions_index["sessions"]:
        return None
    
    session_data = sessions_index["sessions"][session_id]
    
    # Don't allow completing if not in IN_PROGRESS
    if session_data["status"] != LiveSessionStatus.IN_PROGRESS.value:
        return None
    
    session_data["status"] = LiveSessionStatus.COMPLETED.value
    session_data["completed_at"] = datetime.now().isoformat()
    if recording_url:
        session_data["recording_url"] = recording_url
    
    # Create LiveSession object
    session = LiveSession(
        id=session_id,
        curriculum_module_id=session_data["curriculum_module_id"],
        title=session_data["title"],
        description=session_data["description"],
        trainer_id=session_data["trainer_id"],
        session_type=SessionType(session_data["session_type"]),
        max_participants=session_data["max_participants"],
        enrolled_participants=session_data.get("enrolled_participants", 0),
        scheduled_at=datetime.fromisoformat(session_data["scheduled_at"]),
        status=LiveSessionStatus.COMPLETED,
        completed_at=datetime.fromisoformat(session_data["completed_at"]),
        recording_url=session_data.get("recording_url"),
    )
    
    _save_sessions_index(sessions_index)
    return session


def enroll_participant(session_id: str) -> bool:
    """Enroll a participant in a live session."""
    sessions_index = _load_sessions_index()
    
    if session_id not in sessions_index["sessions"]:
        return False
    
    session_data = sessions_index["sessions"][session_id]
    
    if session_data["enrolled_participants"] >= session_data["max_participants"]:
        return False  # at capacity
    
    if session_data["status"] != LiveSessionStatus.SCHEDULED.value:
        return False  # can only enroll in scheduled sessions
    
    session_data["enrolled_participants"] += 1
    
    _save_sessions_index(sessions_index)
    return True


def get_session(session_id: str) -> Optional[LiveSession]:
    """Get a live session by ID."""
    sessions_index = _load_sessions_index()
    
    if session_id not in sessions_index["sessions"]:
        return None
    
    sd = sessions_index["sessions"][session_id]
    
    return LiveSession(
        id=sd["id"],
        curriculum_module_id=sd["curriculum_module_id"],
        title=sd["title"],
        description=sd["description"],
        trainer_id=sd["trainer_id"],
        session_type=SessionType(sd["session_type"]),
        max_participants=sd["max_participants"],
        enrolled_participants=sd.get("enrolled_participants", 0),
        scheduled_at=datetime.fromisoformat(sd["scheduled_at"]),
        status=LiveSessionStatus(sd["status"]),
        started_at=datetime.fromisoformat(sd["started_at"]) if sd.get("started_at") else None,
        completed_at=datetime.fromisoformat(sd["completed_at"]) if sd.get("completed_at") else None,
        recording_url=sd.get("recording_url"),
        chat_log=sd.get("chat_log", []),
        poll_results=sd.get("poll_results"),
    )


def get_module_sessions(module_id: str) -> List[LiveSession]:
    """Get all live sessions for a curriculum module."""
    sessions_index = _load_sessions_index()
    
    sessions = []
    for session_id, sd in sessions_index["sessions"].items():
        if sd["curriculum_module_id"] == module_id:
            sessions.append(get_session(session_id))
    return sessions


def init_live_sessions():
    """Initialize the live session data structures."""
    _load_sessions_index()
    _load_modules_index()


# Export for web app integration
__all__ = [
    'LiveSessionStatus', 'SessionType', 'CurriculumModule', 'LiveSession',
    'create_curriculum_module', 'get_curriculum_module', 'list_curriculum_modules',
    'start_live_session', 'complete_live_session', 'enroll_participant',
    'get_session', 'get_module_sessions', 'init_live_sessions'
]