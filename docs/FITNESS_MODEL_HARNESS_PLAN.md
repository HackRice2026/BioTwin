# Fitness Model Harness Plan

## Core Thesis
The product is not Gemini + ElevenLabs + a 3D avatar. The defensible product is the **fitness harness around the foundation models**.

> The model is replaceable. The coaching system is not.

```text
FOUNDATION MODELS
Gemini / Vision / TTS / Audio2Face
        │
        ▼
FITNESS HARNESS
- user state
- calendar reasoning
- recovery forecast
- workout programming
- training policies
- temporal planning
- scenario simulation
- avatar behavior
- tool execution
- evaluation
        │
        ▼
EMBODIED COACH
```

## 1. User-State Engine
Maintain structured state independent of the LLM:
- sleep
- fatigue
- stress
- soreness
- motivation
- recent workout volume
- training history
- schedule pressure
- available time
- preferred training time
- recent performance

Example:
```json
{
  "sleep_hours": 4.2,
  "fatigue": 0.78,
  "stress": 0.71,
  "motivation": 0.48,
  "soreness": {
    "quads": 0.42,
    "hamstrings": 0.71,
    "chest": 0.18
  },
  "training_load_7d": 0.81,
  "calendar_pressure": 0.74
}
```

## 2. Forecast Engine
Do not only compute readiness now. Compute a day curve:
```text
09:00  72
12:00  65
15:00  51
17:40  84
21:00  47
```

Potential inputs:
- current recovery
- sleep
- calendar density
- meetings/classes
- free windows
- likely stress windows
- training load
- user's historical preferences

Example output:
```json
{
  "best_window": "17:40",
  "window_end": "18:35",
  "expected_readiness": 0.84,
  "confidence": 0.72,
  "reason_codes": [
    "calendar_clear",
    "stress_drop_expected",
    "sufficient_session_duration"
  ]
}
```

Treat this as a planning estimate, not a medically precise prediction.

## 3. Training-Policy Engine
Encode stable coaching rules instead of asking the LLM to rediscover them every turn.

```python
if fatigue > 0.75 and sleep_debt > 0.60:
    volume_multiplier *= 0.70

if soreness["hamstrings"] > 0.80:
    avoid_high_eccentric_hamstring_work = True

if available_minutes < 30:
    session_strategy = "density"

if readiness < 0.45:
    high_intensity_failure_training = False
```

The LLM handles explanation and edge cases. The harness provides stable constraints.

## 4. Planning Engine
Answer:
- WHEN should the user train?
- WHAT should the session be?
- HOW should it change?
- WHY?

Inputs:
```text
calendar
+ forecast readiness
+ training objective
+ previous sessions
+ available duration
+ user state
+ training policy
```

Example:
```json
{
  "training_window": {
    "start": "17:40",
    "end": "18:35"
  },
  "session": "upper_power",
  "expected_duration_minutes": 51,
  "volume_multiplier": 0.82,
  "intensity_multiplier": 0.95,
  "reasoning_summary": [
    "highest readiness window",
    "55-minute calendar opening",
    "lower predicted stress",
    "upper body recovered"
  ]
}
```

This plan becomes the source of truth. Gemini explains it rather than silently replacing it.

## 5. Future-Self / Scenario Engine
Compare alternative decisions.

```text
PATH A — TRAIN NOW
Readiness: 64%
Expected session quality: moderate
Expected evening fatigue: 82%

PATH B — TRAIN 5:40 PM
Readiness: 84%
Expected session quality: high
Expected evening fatigue: 51%
```

This can begin as a deterministic scoring model.

The important behavior is being able to answer:
> "What happens if I train now instead?"

That turns recommendation into **decision simulation**.

## 6. Gemini Reasoning Layer
Give Gemini structured context:
```json
{
  "user_state": {},
  "forecast": {},
  "training_policy": {},
  "calendar": {},
  "current_plan": {}
}
```

Require structured semantic output:
```json
{
  "speech": "I'd wait until 5:40. Your schedule opens up and your predicted readiness improves.",
  "emotion": {
    "energy": 0.67,
    "happiness": 0.42,
    "fatigue": 0.12,
    "stress": 0.08,
    "confidence": 0.92,
    "concern": 0.28
  },
  "action": {
    "type": "POINT_TIMELINE",
    "target": "17:40"
  },
  "gaze": "timeline.17:40"
}
```

Gemini should choose language, reasoning, and semantic actions. It should not directly manipulate bones, morph targets, or raw UI coordinates.

## 7. Embodiment Engine
Translate semantic intent into physical behavior:
- exact animation
- timing
- gaze
- morph values
- posture
- camera transition
- gesture intensity
- movement speed

Principle:
> The LLM chooses meaning. The avatar engine chooses performance.

## 8. Voice + Facial Performance
```text
Gemini
↓
speech text
↓
ElevenLabs TTS
↓
streaming audio
↓
Audio2Face-3D
↓
blendshape stream
↓
Three.js avatar
```

Use the same ElevenLabs stream for browser playback and Audio2Face.

Final face:
```text
lip sync
+ emotion
+ blink
+ microexpression
```

Speech should dominate mouth/jaw. Emotion should mostly influence eyes, brows, cheeks, and mouth corners.

## 9. Tool / Action Layer
The coach should act on the user's world:
- read calendar
- find free windows
- recommend training slot
- reschedule workout
- create workout event
- update workout plan
- retrieve past workout history

The LLM requests semantic actions. The harness validates and executes them.

## 10. Evaluation Harness
Evaluate the system, not just the model.

Checks:
- Did the workout fit the available calendar window?
- Did it overlap an event?
- Did it violate a recovery constraint?
- Did the explanation match the actual plan?
- Did Gemini invent a calendar event?
- Did exercise selection match the user's goal?
- Did adaptation make unnecessary changes?
- Did the avatar point at the item being discussed?
- Did the forecast use real available inputs?
- Did tool execution match the requested action?

Example:
```python
assert session.duration_minutes <= free_window.duration_minutes
assert not calendar.has_collision(session.start, session.end)
assert recommendation.plan_id == explanation.plan_id
```

## 11. Confidence and Evidence
Important recommendations should be traceable.

```json
{
  "recommendation": "train_at_17_40",
  "confidence": 0.74,
  "evidence": [
    "90_minute_calendar_gap",
    "predicted_stress_lower_than_15_00",
    "upper_body_recovered",
    "session_duration_51_minutes"
  ]
}
```

This allows the avatar to explain itself clearly.

## 12. System Architecture
```text
                       USER
                         │
         ┌───────────────┼──────────────┐
         │               │              │
      calendar         body          history
         │               │              │
         └───────────────┼──────────────┘
                         ▼
                FITNESS STATE MODEL
                         │
                         ▼
                   FORECAST ENGINE
                         │
                         ▼
                  PLAN OPTIMIZER
                         │
            ┌────────────┴─────────────┐
            ▼                          ▼
       TRAINING POLICY              Gemini
            │                          │
            └────────────┬─────────────┘
                         ▼
                   COACH ACTION
                         │
          ┌──────────────┼─────────────┐
          ▼              ▼             ▼
        voice          avatar         tools
                                      │
                                  calendar
```

## 13. GTM Harness Analogy
A weak GTM product:
```text
LLM → email
```

A strong one surrounds the model with:
```text
CRM state
account enrichment
lead scoring
company knowledge
workflow rules
sequence state
memory
permissions
tool execution
evaluation
```

Likewise, a weak fitness product:
```text
Gemini → workout
```

A strong one becomes:
```text
calendar
+ user state
+ recovery
+ training history
+ forecast
+ policy
+ planning
+ tool execution
+ embodiment
+ evaluation
```

## 14. Model Independence
Use interfaces so the reasoning model can be swapped.

```ts
interface ReasoningProvider {
  generateCoachAction(context: CoachContext): Promise<CoachAction>;
}
```

Possible providers:
- Gemini
- GPT
- Claude
- local model
- future model

The rest of the system should not care.

## 15. What the Product Actually Owns
The product's durable intelligence should increasingly live in:
```text
user-state representation
forecasting
training policy
planning
scenario comparison
evaluation
behavior orchestration
tool execution
historical personalization
```

Not in one prompt.

The prompt is replaceable. The harness accumulates value.

## 16. Hackathon Pitch
Strong line:
> "Foundation models can talk about fitness. We built the layer that lets them actually coach."

Then show:
```text
FORECAST
↓
PLAN
↓
ADAPT
↓
EXPLAIN
↓
ACT
↓
DEMONSTRATE
```

Another line:
> "The model isn't our product. The coaching harness is."

## 17. Demo Story
User:
> "How's my day looking?"

System retrieves:
- calendar
- current state
- recovery
- training plan

Forecast:
```text
NOW      64%
3 PM     51%
5:40 PM  84%
9 PM     47%
```

Avatar:
> "Don't train right now."

Points to afternoon:
> "Your meetings stack here."

Points to 5:40:
> "This is your best window. I've moved your upper-power session here."

User:
> "What if I train now?"

Scenario engine compares both futures.

Avatar:
> "You can, but you'll probably get a worse session and carry more fatigue into tonight."

User:
> "Show me what we're doing."

Avatar transitions into exercise demonstration.

This demonstrates:
```text
data
→ state
→ forecast
→ policy
→ planning
→ reasoning
→ physical action
```

## 18. Build Priority
### P0 — State
- user state schema
- calendar schema
- workout history schema
- current plan schema

### P1 — Forecast
Build a simple deterministic readiness/availability curve.

### P2 — Policy
Encode a small set of meaningful training adaptation rules.

### P3 — Planner
Select:
- workout time
- workout type
- duration
- adaptation multiplier

### P4 — Gemini Interface
Provide structured context and require structured semantic actions.

### P5 — Embodiment
Map actions into:
- voice
- face
- gaze
- gestures
- body movement
- camera

### P6 — Evaluation
Build deterministic checks around important outputs.

## 19. Do Not Overbuild
For the hackathon, avoid:
- medically validated physiological modeling
- massive sports-science knowledge graphs
- hundreds of rules
- reinforcement-learning planning
- custom forecasting neural networks
- enormous exercise libraries

A simple, explainable harness with a spectacular embodied demo is stronger than an invisible complex backend.

## Final Principle
Do not build:
```text
LLM
↓
fitness answer
```

Build:
```text
USER CONTEXT
↓
STATE
↓
FORECAST
↓
POLICY
↓
PLAN
↓
LLM REASONING
↓
VALIDATION
↓
ACTION
↓
EMBODIED COACH
```

> **Foundation models provide general intelligence. The harness turns that intelligence into reliable domain behavior.**

For this product:

> **The harness is what turns a model that knows fitness into a coach that understands the user over time.**
