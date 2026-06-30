# Experimental Assistant (EA) — Project Brief for Coding Agents

> Historical note: this is an early Web/FastAPI/React-oriented project brief. The current canonical project design is `EA_PROJECT_DESIGN.md`; the current v0.2 planning document is `EA_V0_2_WORK_PLAN.md`.

> Version: v0.1-draft | Last updated: 2026-05-08
> Target: Quick onboarding for Claude Code, Codex, or other coding agents building EA.

---

## 1. What EA Is

EA is a **local-first, human-in-the-loop AI research console** for experimental scientists — starting with materials science.

One-liner: *EA helps researchers organize experiment logs, process data, call modular scientific skills, and generate traceable analysis reports.*

## 2. What EA Is NOT

- NOT a fully autonomous scientist
- NOT just a chatbot or a script collection
- NOT a lab-equipment controller (v1)
- NOT a single Claude Code skill
- Raw data is NEVER modified

## 3. Five Core Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | Human-in-the-loop by default | AI assists, key steps require user confirmation |
| 2 | Experiment-centered workflow | Core entities: project, experiment, sample, data file, result |
| 3 | Traceability & provenance | Every output links back to inputs, skills, params, decisions |
| 4 | Modular skill-based design | Scientific capabilities are replaceable, pluggable skills |
| 5 | Local-first, researcher-controlled | Local storage, raw data read-only |

## 4. Domain Entities

| Entity | Description |
|--------|-------------|
| Project | Top-level research project container |
| Experiment | Structured experiment record card |
| Sample | Physical sample with ID and material system |
| Material System | E.g., MoS2 — cross-experiment grouping |
| Process Condition | Temp, time, atmosphere, etc. |
| Characterization File | Raw data file (CSV/TXT/XLSX) — READ-ONLY |
| Data-Processing Result | Plot, processed CSV, metadata, summary |
| Literature Record | PDF summaries, linked to experiments |
| Report | Markdown/HTML output with provenance |
| User Review Decision | Confirm/edit/reject at each review gate |
| Skill | Registered, callable functional unit with metadata |

**Entity relationships:**

```
Project ──< Experiment ──< Sample ── Material System
                │
                ├── Process Condition
                ├── Characterization File ──< Data-Processing Result
                ├── Literature Record
                └── Report

Skill (independent) ──> Data-Processing Result (when executed)

User Review Decision (cross-cuts)
  └── gates: Experiment, Data-Processing Result, Report, Literature Record
```

**Review status flow:** `draft → needs_review → user_confirmed | user_rejected → archived`

## 5. Target Users & Problems

**Primary:** Materials-science researchers handling Excel logs, Raman, PL, XRD, SEM/TEM, CVD growth logs, annealing records.

**Future:** Chemistry, physics, biology, electrochemistry, device research.

**Five pain points:**

| # | Pain Point | EA Solution |
|---|-----------|-------------|
| 1 | Experiment records scattered across folders/formats | Convert unstructured notes → structured records |
| 2 | Data processing is repetitive and untracked | Auto-process + save code/params/outputs |
| 3 | AI outputs are black-box | Show full workflow trace: files→skill→params→result→review |
| 4 | Literature disconnected from experiments | Link local literature notes to experiments and data |
| 5 | Research memory is fragile | Build persistent project-level memory |

## 6. Core Workflow (12 Steps)

| Step | Who | Action | Channel |
|------|-----|--------|---------|
| 1 | User | Create/open a research project | Web |
| 2 | User | Input experiment note or upload files | Web (v0.2+: + mobile) |
| 3 | EA | Parse note, detect entities | Backend auto |
| 4 | EA→User | Show extracted fields, request confirmation | Web (v0.2+: + mobile push) |
| 5 | User | Request data file processing | Web (v0.2+: + mobile) |
| 6 | EA | Identify file type, suggest processing plan | Web (v0.2+: + mobile) |
| 7 | User | Confirm data fields and parameters | Web (v0.2+: + mobile) |
| 8 | EA | Run the relevant skill | Backend auto |
| 9 | EA | Generate plots, processed data, draft analysis | Backend auto |
| 10 | EA→User | Show workflow trace and results | Web (full) / Mobile (summary) |
| 11 | User | Confirm, edit, or reject interpretation | Web (v0.2+: + mobile) |
| 12 | EA | Write confirmed results to project memory + reports | Backend auto |

## 7. Six Mandatory Review Gates

Before proceeding past each of these, EA MUST stop and wait for user input:

| # | Gate | What Is Reviewed |
|---|------|-----------------|
| 1 | Task plan | Multi-step workflow plan before execution |
| 2 | Field extraction | Editable structured fields after parsing |
| 3 | Data columns | x/y column selection after file read |
| 4 | Parameters | Smoothing, baseline, normalization, fitting model |
| 5 | Scientific interpretation | Observation vs. calculation vs. hypothesis vs. conclusion |
| 6 | Memory write | Before saving interpretation to long-term project memory |

## 8. MVP Scope (v0.1)

**Goal:** One complete loop — log input → file upload → AI parsing → data plotting → draft analysis → human review → report → memory update.

### 8.1 MVP Skills (4)

| Skill | Input | Output | Key Behaviors |
|-------|-------|--------|---------------|
| Experiment Log Structuring | Free-text note, optional sample ID, date, files | Structured JSON experiment card | Extract entities, wait for user edit/confirm |
| Generic Data Reader & Plotter | CSV, TXT, Excel | Plot PNG, processed CSV, metadata JSON, Markdown summary | Detect sheets/columns, ask user to confirm x/y |
| Raman Analysis (Demo) | Raman spectrum files (CSV/TXT) | Spectra plot, peak list, cautious analysis summary | Baseline correction, peak detection, multi-explanation output |
| Report Generation | Confirmed log + processed data + reviewed interpretation | Markdown or HTML report with 9 sections | Include provenance log section |

### 8.2 v0.1 Success Criteria (10 items)

1. Create a local project
2. Accept an experiment note
3. Extract structured experiment fields
4. Let user review and edit fields
5. Upload and preview CSV/Excel/TXT data
6. Generate plot from user-confirmed columns
7. Run at least one characterization demo skill (Raman preferred)
8. Generate a short report
9. Show a workflow trace
10. Save outputs without modifying raw data

### 8.3 What v0.1 Does NOT Include

- Lab-equipment control
- Automatic experiment decision-making
- Multi-user permissions
- Cloud deployment
- Large-scale RAG
- Auto online paper search
- Too many characterization modules at once
- Overly complex DB design
- UI perfection before workflow works
- Mobile access (WeChat/Feishu) → deferred to v0.2+

## 9. Future Capabilities (post-MVP)

**Skills to add:** XRD analysis, PL spectra, AFM analysis, electrochemical data, SEM/TEM image annotation, batch experiment comparison, PDF literature summarization, local literature Q&A, project progress summary, group meeting report drafts, Obsidian/Zotero integration, folder watcher auto-import.

**Platform:** Mobile access via WeChat/Feishu (v0.2+).

## 10. Tech Architecture

### 10.1 Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React (Vite) | Desktop-app feel, rich component ecosystem, multi-user ready |
| Backend | FastAPI (Python) | Native Python science ecosystem integration (numpy, scipy, pandas, matplotlib) |
| Storage | Filesystem + SQLite | Local-first, simple, portable |
| LLM | OpenAI API (GPT model, specific version TBD) | Swappable via adapter layer; fallback: DeepSeek API |
| Skills | Python scripts, registered via YAML metadata | Extensible, replaceable |

### 10.2 Architecture Layers

```
EA Product
├── React UI
├── FastAPI Backend
├── Workflow Orchestrator
├── Skill Registry
├── Local Scientific Skills (Python, YAML-metadata)
├── Agent Adapter Layer (OpenAI / DeepSeek / local-script)
├── Storage & Provenance
└── (v0.2+) Message Gateway (WeChat/Feishu webhooks)
```

### 10.3 Repository Structure

```
experimental-assistant/
├── README.md
├── docs/                        # Design docs, briefs, maps
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                 # REST endpoints
│   │   ├── core/                # Config, settings
│   │   ├── models/              # Pydantic/SQLAlchemy models
│   │   ├── services/            # Business logic
│   │   ├── storage/             # File & DB access
│   │   ├── skills/              # Skill registry & execution
│   │   ├── provenance/          # Workflow trace logging
│   │   └── agent_adapters/      # LLM provider adapters
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/               # 6 page components
│   │   ├── components/          # Shared UI components
│   │   ├── workflow/            # Workflow step rendering
│   │   ├── skill-library/       # Skill catalog UI
│   │   └── project-memory/      # Memory viewer UI
│   └── package.json
├── skills/                      # Independent skill packages
│   ├── experiment_log/
│   ├── generic_data_plot/
│   ├── raman_analysis/
│   └── report_generation/
├── examples/                    # Sample project & data
├── data/
│   ├── raw/                     # READ-ONLY
│   ├── processed/
│   ├── reports/
│   └── project_memory/
└── outputs/
```

## 11. UI Pages (6 + 1 deferred)

| Page | Purpose | Key Features |
|------|---------|-------------|
| Home / Research Console | Main interaction area | Text input, file upload, task plan display, confirm buttons, output preview |
| Project Workspace | Project overview | Experiments, samples, files, reports, recent workflows |
| Experiment Log | Log management | New note, review AI fields, edit, link files, confirm |
| Data Processing | Data interaction | Upload, preview table, select x/y columns, config params, display plots, save |
| Skill Library | Skill catalog | Name, description, I/O types, risk level, deps, enable/disable |
| Workflow Viewer | Provenance trace | Steps, tools used, I/O files, params, warnings, user decisions |
| *(v0.2+)* Mobile Chat | Mobile access | Chat-style note input, file upload, short commands, review confirmations |

## 12. Storage Rules

1. Raw files are read-only
2. Processed files go to a separate folder
3. Every processed output must have an accompanying metadata file
4. Every AI-generated interpretation must have a review status
5. Hypotheses must NOT be stored as confirmed facts without user confirmation
6. Reports must include provenance info

**Review status enum:** `draft | needs_review | user_confirmed | user_rejected | archived`

## 13. Skill Specification Standard

Every skill MUST have a `skill.yaml`:

```yaml
name: raman_analysis
display_name: Raman Spectrum Analysis
category: data_processing
description: Load Raman spectra, plot, detect peaks, generate cautious analysis.
input_types: [csv, txt, xlsx]
output_types: [png, csv, markdown]
requires_review: true
risk_level: medium
entrypoint: python skills/raman_analysis/run.py
dependencies: [pandas, numpy, scipy, matplotlib]
```

Every skill MUST return:

```json
{
  "status": "success",
  "outputs": {
    "figure": "outputs/raman_plot.png",
    "processed_data": "outputs/raman_processed.csv",
    "summary": "outputs/raman_summary.md"
  },
  "parameters": {
    "baseline_correction": "none",
    "normalization": "max_intensity"
  },
  "warnings": ["Peak interpretation requires user review."],
  "requires_user_review": true
}
```

## 14. Scientific Safety Rules

**Behavior rules:**
1. Always separate: observation | calculation | interpretation | hypothesis | conclusion
2. Never overclaim from a single data type
3. Never claim causation without strong evidence
4. Never silently mix literature from different material systems
5. Always preserve raw data
6. Show uncertainty when interpretation is ambiguous
7. Always ask user before writing conclusions to project memory

**Recommended language:** "may indicate", "is consistent with", "could be related to", "requires further confirmation"

**Forbidden language:** "this proves X", "this confirms X", "this mechanism is certain"

## 15. Development Principles for Coding Agents

1. Preserve the product philosophy above
2. Ask clarifying questions only when necessary
3. Prefer small, testable implementation steps
4. Keep raw data read-only
5. Add metadata and provenance for every generated file
6. Avoid over-engineering early architecture
7. Maintain readable documentation
8. Create example data and example workflows
9. Keep the user involved in scientific interpretation choices
10. Treat EA as a research product, not just a coding exercise

## 16. LLM Provider Strategy

- **v0.1:** OpenAI API (GPT model, exact version to be decided at project start) — pay-per-use API, NOT included in ChatGPT Plus/Pro subscription
- **DeepSeek API** is the cost-effective fallback (~¥1/1M tokens)
- Architecture uses an **Agent Adapter Layer** so providers are swappable
- Local script mode available for deterministic tasks (e.g., file parsing)

## 17. Key Design Decisions (from user)

- Mobile access (WeChat/Feishu) is deferred to v0.2+
- MVP proves the loop, but architecture must support infinite skill expansion (XRD, AFM, PL, SEM, etc.)
- Final product is for real users, not just personal tooling — React+FastAPI chosen for product quality
