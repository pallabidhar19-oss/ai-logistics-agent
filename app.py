# ─────────────────────────────────────────────────────────────────────────────
#  AI Logistics Operations Agent
#  Google All Things Agentic Hackathon — TASKMASTER track
#  Stack: Gemini 2.0 Flash · Google GenAI SDK · Google Cloud Firestore
# ─────────────────────────────────────────────────────────────────────────────

import os, json, datetime
import streamlit as st
import google.generativeai as genai

# ── Page ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Logistics Operations Agent",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── API Key ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ── Firestore (optional – graceful fallback to local JSON) ────────────────────
_db = None
FIRESTORE_BACKEND = "Local JSON"
try:
    from google.cloud import firestore as _fs
    _db = _fs.Client()
    FIRESTORE_BACKEND = "Google Cloud Firestore"
except Exception:
    pass

# ── Simulated logistics data ──────────────────────────────────────────────────
FLEET = [
    {"id": "V-001", "type": "Heavy Truck",  "capacity": 5000, "available": True,  "base": "Kolkata",    "factor": 1.00},
    {"id": "V-007", "type": "Medium Truck", "capacity": 2000, "available": True,  "base": "Kolkata",    "factor": 1.10},
    {"id": "V-012", "type": "Express Van",  "capacity":  800, "available": True,  "base": "Bhubaneswar","factor": 1.30},
    {"id": "V-017", "type": "Heavy Truck",  "capacity": 5000, "available": True,  "base": "Kolkata",    "factor": 0.95},
    {"id": "V-023", "type": "Refrigerated", "capacity": 1500, "available": False, "base": "Kolkata",    "factor": 1.20},
]

ROUTE_KM = {
    ("Kolkata","Bengaluru"): 1870, ("Kolkata","Mumbai"):    2050,
    ("Kolkata","Delhi"):     1500, ("Mumbai","Delhi"):      1400,
    ("Bengaluru","Delhi"):   2100, ("Kolkata","Chennai"):   1670,
    ("Mumbai","Bengaluru"):   980, ("Chennai","Delhi"):     2200,
    ("Hyderabad","Delhi"):   1500, ("Kolkata","Hyderabad"): 1200,
}

def _km(a: str, b: str) -> float:
    a, b = a.strip().title(), b.strip().title()
    return ROUTE_KM.get((a,b)) or ROUTE_KM.get((b,a)) or 1200.0

# ── Per-run state (cleared before each agent run) ─────────────────────────────
_activity: list = []
_outputs:  dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AGENT TOOL FUNCTIONS  — passed directly to Gemini as tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_shipment(
    origin: str,
    destination: str,
    cargo_kg: float,
    priority: str,
    delivery_hours: int,
) -> dict:
    """
    Analyze the shipment request. Compute route distance, minimum transit time,
    and overall feasibility. Call this FIRST.
    """
    dist   = _km(origin, destination)
    min_h  = round(dist / 60.0, 1)
    result = {
        "origin": origin, "destination": destination,
        "cargo_kg": cargo_kg, "priority": priority,
        "requested_hours": delivery_hours, "route_km": dist,
        "min_transit_hours": min_h,
        "feasibility": "Feasible" if delivery_hours >= min_h else "Tight – express routing needed",
    }
    _activity.append("📦 Shipment requirements analyzed")
    _outputs["analyze"] = result
    return result


def check_fleet_availability(origin: str, min_capacity_kg: float) -> dict:
    """
    Check which vehicles are currently available and have sufficient capacity
    for the cargo weight. Call this SECOND.
    """
    available = [v for v in FLEET if v["available"] and v["capacity"] >= min_capacity_kg]
    result    = {"available_vehicles": available, "count": len(available)}
    _activity.append("🚛 Fleet availability checked")
    _outputs["fleet"] = result
    return result


def evaluate_delivery_constraints(
    vehicle_id:     str,
    distance_km:    float,
    priority:       str,
    delivery_hours: int,
) -> dict:
    """
    Evaluate whether a specific vehicle meets the delivery window.
    Select the best vehicle from check_fleet_availability results and call this THIRD.
    """
    vehicle = next((v for v in FLEET if v["id"] == vehicle_id), None)
    if not vehicle:
        return {"error": f"Vehicle {vehicle_id} not found."}
    speed  = 68.0 if priority == "High" else 55.0
    eta    = round((distance_km / speed) * vehicle["factor"], 1)
    result = {
        "vehicle_id":   vehicle_id,
        "vehicle_type": vehicle["type"],
        "eta_hours":    eta,
        "required_hours": delivery_hours,
        "meets_window": eta <= delivery_hours,
        "buffer_hours": round(delivery_hours - eta, 1),
    }
    _activity.append("⏱️ Delivery constraints evaluated")
    _outputs["eval"] = result
    return result


def generate_dispatch_order(
    vehicle_id:  str,
    origin:      str,
    destination: str,
    cargo_kg:    float,
    priority:    str,
    eta_hours:   float,
) -> dict:
    """
    Generate the official dispatch order for the selected vehicle. Call this FOURTH.
    """
    vehicle = next((v for v in FLEET if v["id"] == vehicle_id), None)
    order   = {
        "decision_id":  f"DEC-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "timestamp":    datetime.datetime.utcnow().isoformat(),
        "status":       "DISPATCHED",
        "vehicle_id":   vehicle_id,
        "vehicle_type": vehicle["type"] if vehicle else "Unknown",
        "route":        f"{origin} → {destination}",
        "cargo_kg":     cargo_kg, "priority": priority, "eta_hours": eta_hours,
        "note": f"{priority}-priority shipment assigned to {vehicle_id}. ETA: {eta_hours} hrs.",
    }
    _activity.append("✅ Dispatch order generated")
    _outputs["decision"] = order
    return order


def log_to_persistent_store(
    decision_id: str,
    vehicle_id:  str,
    route:       str,
    cargo_kg:    float,
    eta_hours:   float,
    status:      str,
) -> dict:
    """
    Persist the dispatch decision to Google Cloud Firestore.
    Falls back to local JSON if Firestore credentials are not configured.
    Call this FIFTH (last).
    """
    doc = {
        "decision_id": decision_id, "vehicle_id": vehicle_id,
        "route": route, "cargo_kg": cargo_kg,
        "eta_hours": eta_hours, "status": status,
        "logged_at": datetime.datetime.utcnow().isoformat(),
    }
    if _db is not None:
        try:
            _, ref = _db.collection("logistics_decisions").add(doc)
            result = {"stored": True, "backend": "Google Cloud Firestore", "doc_id": ref.id}
            _activity.append(f"☁️  Logged to Firestore  (doc: {ref.id[:10]}…)")
            _outputs["log"] = result
            return result
        except Exception:
            pass
    # ── Local JSON fallback ────────────────────────────────────────────────
    path     = "decisions.json"
    existing = json.load(open(path)) if os.path.exists(path) else []
    existing.append(doc)
    json.dump(existing, open(path, "w"), indent=2, default=str)
    result = {"stored": True, "backend": "Local JSON (→ Firestore in production)"}
    _activity.append("💾 Decision logged to local store")
    _outputs["log"] = result
    return result


TOOLS = [
    analyze_shipment,
    check_fleet_availability,
    evaluate_delivery_constraints,
    generate_dispatch_order,
    log_to_persistent_store,
]

SYSTEM_PROMPT = """You are an autonomous AI Logistics Operations Agent for a freight company.

When given a shipment request you MUST call these 5 tools IN EXACT ORDER:
1. analyze_shipment              — compute route distance and feasibility
2. check_fleet_availability     — find vehicles that meet cargo capacity
3. evaluate_delivery_constraints — check whether the best vehicle meets the window
4. generate_dispatch_order       — create the official dispatch record
5. log_to_persistent_store       — save the decision to Firestore / local store

After all 5 tool calls complete, write a 3–5 sentence operations summary:
- What action was recommended and why
- Which vehicle was assigned and the ETA
- Any risk or note the ops team should know

Never skip a step. Never call a step out of order. Always complete all 5."""


def run_agent(origin, destination, cargo_kg, priority, delivery_hours):
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        tools=TOOLS,
        system_instruction=SYSTEM_PROMPT,
    )
    chat   = model.start_chat(enable_automatic_function_calling=True)
    prompt = (
        f"Process this shipment request:\n"
        f"Origin: {origin}\n"
        f"Destination: {destination}\n"
        f"Cargo weight: {cargo_kg} kg\n"
        f"Priority: {priority}\n"
        f"Required delivery window: {delivery_hours} hours\n\n"
        f"Run all 5 tools in order, then give the operations summary."
    )
    response = chat.send_message(prompt)
    return response.text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STREAMLIT UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.markdown("""
<style>
  .tag {
    display: inline-block;
    background: #e8f0fe; color: #1a56db;
    border-radius: 5px; padding: 2px 10px;
    font-size: 0.82rem; margin-right: 6px; font-weight: 600;
  }
  .step { font-size: 1.05rem; line-height: 1.8; }
  .summary-box {
    background: #f8f9ff; border-left: 4px solid #4f6ef7;
    border-radius: 0 8px 8px 0; padding: 1rem 1.25rem;
    margin-top: 0.5rem;
  }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🚚  AI Logistics Operations Agent")
st.markdown(
    '<span class="tag">Gemini 2.0 Flash</span>'
    '<span class="tag">Google GenAI SDK</span>'
    f'<span class="tag">{FIRESTORE_BACKEND}</span>'
    '<span class="tag">TASKMASTER Track</span>',
    unsafe_allow_html=True,
)
st.caption("Autonomous multi-step logistics dispatch agent — Google All Things Agentic Hackathon")
st.divider()

# ── Layout ─────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1.4], gap="large")

with left:
    st.subheader("📋 Shipment Request")
    with st.form("shipment_form"):
        origin      = st.text_input("Origin City",       value="Kolkata")
        destination = st.text_input("Destination City",  value="Bengaluru")
        cargo_kg    = st.number_input("Cargo Weight (kg)", 50.0, 10000.0, 1200.0, 50.0)
        priority    = st.selectbox("Priority", ["High", "Medium", "Low"])
        del_hours   = st.slider("Delivery Window (hours)", 12, 168, 48, 4)
        submitted   = st.form_submit_button(
            "🤖  Run Logistics Agent", type="primary", use_container_width=True
        )

    st.divider()
    st.markdown("**Architecture**")
    st.markdown("""
```
Streamlit UI
    ↓ shipment request
Google GenAI SDK (Python)
    ↓ tool calls
Gemini 2.0 Flash
    ↓ function calls
Logistics Tools (5 steps)
    ↓ decision record
Google Cloud Firestore
    ↓ confirmation
Streamlit UI (result)
```
""")

# ── Agent execution + results ──────────────────────────────────────────────────
with right:
    if not submitted:
        st.info("👈  Fill in the shipment details and click **Run Logistics Agent**.")
        st.markdown("**What the agent does autonomously:**")
        st.markdown("""
1. 📦 Analyzes the shipment & route
2. 🚛 Checks fleet availability
3. ⏱️ Evaluates delivery constraints
4. ✅ Generates the dispatch order
5. ☁️  Logs the decision to Firestore
""")
    else:
        if not GEMINI_API_KEY:
            st.error("⚠️  Set `GEMINI_API_KEY` in your environment or `.env` file.")
            st.stop()

        _activity.clear()
        _outputs.clear()

        with st.spinner("🤖  Agent is working through all 5 steps…"):
            try:
                summary = run_agent(origin, destination, cargo_kg, priority, del_hours)
            except Exception as exc:
                st.error(f"Agent error: {exc}")
                st.exception(exc)
                st.stop()

        st.success("✅  Agent completed all 5 steps")

        # ── Activity log ───────────────────────────────────────────────────────
        st.subheader("Agent Activity")
        for step in _activity:
            st.markdown(f'<div class="step">{step}</div>', unsafe_allow_html=True)

        st.divider()

        # ── Dispatch metrics ───────────────────────────────────────────────────
        if "decision" in _outputs:
            d = _outputs["decision"]
            st.subheader("Dispatch Decision")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Vehicle",     d["vehicle_id"])
            m2.metric("Type",        d["vehicle_type"])
            m3.metric("ETA",         f"{d['eta_hours']} hrs")
            m4.metric("Priority",    d["priority"])
            with st.expander("📄 Full dispatch record"):
                st.json(d)

        # ── Operations summary ─────────────────────────────────────────────────
        st.subheader("Operations Summary")
        st.markdown(f'<div class="summary-box">{summary}</div>', unsafe_allow_html=True)

        # ── Storage confirmation ───────────────────────────────────────────────
        if "log" in _outputs:
            log = _outputs["log"]
            if "Firestore" in log.get("backend",""):
                st.success(f"☁️  Persisted to {log['backend']}  •  doc: {log.get('doc_id','')[:12]}…")
            else:
                st.info(f"📁  Saved: {log.get('backend','')}  (configure Firestore for cloud persistence)")

        # ── Route info ─────────────────────────────────────────────────────────
        if "analyze" in _outputs:
            a = _outputs["analyze"]
            with st.expander("🗺️ Route analysis details"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Route distance", f"{a['route_km']} km")
                c2.metric("Min transit",    f"{a['min_transit_hours']} hrs")
                c3.metric("Feasibility",    a["feasibility"])
