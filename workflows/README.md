# WAT Framework — Layer 1: Workflows

## What Are Workflows?

Workflows are the **instruction layer** of the WAT (Workflows, Agents, Tools) architecture. They are Standard Operating Procedure (SOP) documents that describe **what** should happen in each major system flow, **why** it happens, and **which tools** execute each step.

Workflows do not contain executable code. They are plain-language references that map directly to service modules (tools) in `backend/app/services/`.

## How the Layers Connect

```
Layer 1: Workflows (this directory)
  Documents that define objectives, triggers, inputs, steps, outputs, and edge cases.

Layer 2: Agents (the decision-maker)
  Reads workflows, orchestrates tool calls, handles branching and failure.

Layer 3: Tools (the execution)
  Deterministic service modules in backend/app/services/ that perform the actual work.
```

## Workflow Index

| Workflow | File | Primary Services |
|----------|------|-----------------|
| Onboard Pet Parent | `onboard_pet_parent.md` | onboarding.py, whatsapp_sender.py |
| Record Preventive Event | `record_preventive_event.md` | document_upload.py, gpt_extraction.py, preventive_calculator.py, conflict_engine.py |
| Handle Conflict | `handle_conflict.md` | conflict_engine.py, conflict_expiry.py, whatsapp_sender.py |
| Send Reminder | `send_reminder.md` | reminder_engine.py, whatsapp_sender.py |
| Process Document Upload | `process_document_upload.md` | document_upload.py, gpt_extraction.py |
| Handle Reminder Response | `handle_reminder_response.md` | reminder_response.py, preventive_calculator.py |
| Resolve Conflict Expiry | `resolve_conflict_expiry.md` | conflict_expiry.py |

## Principles

- Each workflow maps to one or more service modules in `backend/app/services/`.
- Workflows are kept current as the system evolves.
- Edge cases and failure handling are documented explicitly.
- No business logic lives outside of workflows and their corresponding tools.
