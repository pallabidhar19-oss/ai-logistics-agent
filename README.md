# 🚚 AI Logistics Operations Agent

**Google All Things Agentic Hackathon — TASKMASTER Track**

An autonomous multi-step AI agent that processes freight shipment requests end-to-end:
analyzes routes, checks fleet availability, evaluates delivery constraints, generates a
dispatch order, and persists the decision to Google Cloud Firestore — without a human
in the loop.

---

## Google Technology Stack ✅

| Requirement | What we use |
|---|---|
| **Gemini model** | `gemini-2.0-flash` via the Gemini API |
| **Google Agent Framework** | Google GenAI SDK (`google-generativeai`) with automatic function calling |
| **Google Cloud Infrastructure** | Google Cloud Firestore (Native mode) for persistent decision logging |

---

## What the agent does (TASKMASTER)

The agent autonomously works through **5 tool calls** in sequence for every shipment request:

```
1. analyze_shipment              → route distance, feasibility
2. check_fleet_availability      → vehicles with sufficient capacity
3. evaluate_delivery_constraints → ETA check against delivery window
4. generate_dispatch_order       → official dispatch record (decision_id, vehicle, ETA)
5. log_to_persistent_store       → write to Google Cloud Firestore
```

This is a real agentic workflow — not a chatbot. The agent decides which vehicle to assign,
checks whether it meets the SLA, and takes action (logging to Firestore) autonomously.

---

## Architecture

```
Streamlit UI (browser)
      ↓  shipment request
Google GenAI SDK  ──►  Gemini 2.0 Flash
                              ↓  function_call[]
                        Logistics Tools (Python)
                              ↓  dispatch record
                    Google Cloud Firestore
                              ↓  doc_id
Streamlit UI (result + ops summary)
```

---

## Quick start (local)

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/ai-logistics-agent.git
cd ai-logistics-agent
pip install -r requirements.txt
```

### 2. Get a Gemini API key (free)

1. Go to https://aistudio.google.com/app/apikey
2. Click **Create API key**
3. Copy it

### 3. Configure

```bash
cp .env.example .env
# Open .env and paste your key as GEMINI_API_KEY=...
```

### 4. Run

```bash
streamlit run app.py
```

Open http://localhost:8501, enter a shipment, click **Run Logistics Agent**.

---

## Optional: enable Firestore persistence

1. Create a Google Cloud project at https://console.cloud.google.com
2. Enable Firestore API → create a database in **Native mode**
3. Create a service account, download the JSON key
4. Set the env var:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
   ```
5. Re-run the app — the activity log will show "☁️ Logged to Firestore"

Without this, the app falls back to a local `decisions.json` file automatically.

---

## Hackathon context

This project was created for the Google All Things Agentic Hackathon (August 2026).
The logistics domain was chosen to demonstrate a realistic TASKMASTER scenario:
a high-stakes, multi-step workflow where each tool call depends on the previous result
and the agent must produce an operational action (a dispatch order), not just a text answer.

No pre-existing application code was reused in this submission.
