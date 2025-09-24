from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import os, re

app = FastAPI(title="Finspo AI Chatbot")

# CORS (lock down in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve front-end from current folder
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
def root():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"status":"Finspo AI Chatbot Running"})

# ---------------- Demo session store ----------------
SESSIONS: Dict[str, Dict] = {}

DOC_CHECKLIST = {
    "first home": [
        "Photo ID (passport/driver licence)",
        "Income docs: last 2 payslips OR last 2 tax returns (self-employed)",
        "Bank statements (last 3 months)",
        "Savings history & deposit amount",
        "Property details (if found)",
    ],
    "refinance": [
        "Photo ID",
        "Income docs: payslips/tax returns",
        "Recent home loan statement(s)",
        "Rates notice / insurance",
        "Bank statements (last 3 months)",
    ],
    "investor": [
        "Photo ID",
        "Income docs + rental income statements",
        "Existing loan statements",
        "Bank statements (last 3 months)",
        "Property portfolio details",
    ],
    "upgrade": [
        "Photo ID",
        "Income docs",
        "Current mortgage statements",
        "Estimated sale price / equity",
        "Property preferences",
    ],
    "construction": [
        "Photo ID",
        "Income docs",
        "Bank statements (last 3 months)",
        "Land contract & build contract",
        "Plans & specifications (if available)",
    ],
    "default": [
        "Photo ID",
        "Income docs: payslips/tax returns",
        "Bank statements (last 3 months)",
        "Property details (if available)",
    ],
}

ADVICE_KEYWORDS = [
    "best loan","which bank","which lender","recommend",
    "rate","interest rate","serviceability","can i borrow",
    "how much can i borrow","compare lenders","is this suitable",
]

GOAL_OPTIONS = ["First home","Refinance","Investor","Upgrade","Construction"]
TIMELINE_OPTIONS = ["ASAP (0–1 month)","Soon (1–3 months)","Planning (3–6 months)","Exploring (6+ months)"]

# ---------------- Helpers ----------------
def classify_intent(msg: str) -> str:
    m = msg.lower()
    if any(k in m for k in ADVICE_KEYWORDS):
        return "escalate"
    return "freeform"

def extract_name(text: str) -> Optional[str]:
    t = text.strip()
    m = re.search(r"(?:i\s*am|i'm|my name is)\s+([A-Za-z][A-Za-z\-\s']{1,40})", t, re.I)
    if m:
        return m.group(1).strip().split()[0].capitalize()
    if re.fullmatch(r"[A-Za-z][A-Za-z\-\']{1,19}", t):
        return t.capitalize()
    return None

def checklist_for_goal(goal: Optional[str]) -> List[str]:
    key = (goal or "").lower()
    for k in DOC_CHECKLIST:
        if k in key:
            return DOC_CHECKLIST[k]
    return DOC_CHECKLIST["default"]

def next_stage(s: Dict) -> str:
    if not s.get("name"): return "ask_name"
    if not s.get("goal"): return "ask_goal"
    if not s.get("timeline"): return "ask_timeline"
    return "assist"

# ---------------- Schemas ----------------
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str
    escalation: bool = False
    chips: List[str] = []

class PrimeRequest(BaseModel):
    session_id: str
    goal: Optional[str] = None
    timeline: Optional[str] = None

class PrimeResponse(BaseModel):
    ok: bool = True

# ---------------- API ----------------
@app.post("/prime", response_model=PrimeResponse)
def prime(req: PrimeRequest):
    """Wizard primes non-sensitive context before chat opens."""
    s = SESSIONS.setdefault(req.session_id, {"name": None, "goal": None, "timeline": None, "history": []})
    if req.goal: s["goal"] = req.goal
    if req.timeline: s["timeline"] = req.timeline
    return PrimeResponse(ok=True)

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    s = SESSIONS.setdefault(req.session_id, {"name": None, "goal": None, "timeline": None, "history": []})
    user_msg = req.message.strip()
    s["history"].append({"role":"user","content":user_msg})

    # Compliance guardrails
    if classify_intent(user_msg) == "escalate":
        return ChatResponse(
            reply=("I can’t provide credit advice here. I can connect you with a Finspo broker who’ll act in your Best Interests. "
                   "Would you like me to arrange a quick call?"),
            escalation=True,
            chips=["Book a broker call", "Not now"]
        )

    stage = next_stage(s)

    # 1) Ask for first name inside the chat
    if stage == "ask_name":
        nm = extract_name(user_msg)
        if nm and user_msg.lower() != "start":
            s["name"] = nm
            stage = next_stage(s)
        else:
            return ChatResponse(
                reply=("Hi! I’m **Finny the Peacock**. To personalise things, what’s your first name? "
                       "You can say, for example: **I’m Alex**."),
                chips=["I’m Alex","My name is Sam"]
            )

    # 2) Ask goal if wizard didn’t supply it (fallback)
    if stage == "ask_goal":
        lower = user_msg.lower()
        inferred = next((g for g in GOAL_OPTIONS if g.split()[0].lower() in lower), None)
        if inferred:
            s["goal"] = inferred
            stage = next_stage(s)
        else:
            return ChatResponse(
                reply=f"Nice to meet you, {s['name']}! What brings you in today?",
                chips=GOAL_OPTIONS
            )

    # 3) Ask timeline if wizard didn’t supply it (fallback)
    if stage == "ask_timeline":
        lower = user_msg.lower()
        chosen = next((t for t in TIMELINE_OPTIONS if t.split()[0].lower() in lower or t.lower() in lower), None)
        if chosen:
            s["timeline"] = chosen
            stage = next_stage(s)
        else:
            return ChatResponse(
                reply="Great. When are you hoping to move ahead?",
                chips=TIMELINE_OPTIONS
            )

    # 4) Assist: case-brief aligned content (documents/process/handoff)
    if stage == "assist":
        cl = checklist_for_goal(s.get("goal"))
        bullets = "• " + "\n• ".join(cl)
        reply = (
            f"Thanks {s['name']} — got it: **{s.get('goal','(goal not set)')}**, timeline **{s.get('timeline','(timeline not set)')}**.\n\n"
            f"Here’s a quick document checklist to fast-track things:\n{bullets}\n\n"
            "I can also walk you through the process, share portal setup steps, or connect you with a broker when you’re ready."
        )
        s["history"].append({"role":"assistant","content":reply})
        return ChatResponse(
            reply=reply,
            chips=["What documents do I need?", "What’s the process?", "Book a broker call"]
        )

    # Fallback
    return ChatResponse(
        reply=("I can help with general questions about the process and documents, or get you set up in the portal. "
               "Tell me your first name to begin (e.g., **I’m Alex**)."),
        chips=["I’m Alex","First home","Refinance"]
    )

@app.get("/health")
def health():
    return {"ok": True}
