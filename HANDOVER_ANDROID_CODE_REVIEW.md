# Android Code Review Automation System - Handover Document

**Project Owner:** Mehrosh  
**Status:** POC (Production-ready)  
**Stack:** Python FastAPI + React + Docker  
**Last Updated:** July 23, 2026

---

## 📋 Executive Summary

Build a **web application** that automates Android code review scoring by:
1. Uploading Android project ZIP + review template Excel
2. Analyzing code with Azure OpenAI (GPT-4o-mini)
3. Scoring against 6 review categories
4. Populating the Excel sheet while preserving formatting
5. Showing live progress + final performance metrics

---

## 🎯 Scope & Requirements

### Functional Requirements

**Core Workflow:**
- Web interface: Upload Android ZIP + Excel template
- Backend: Extract, analyze, score, populate Excel
- Output: Downloadable Excel with filled-in scores & remarks
- Empty fields: Leave unscored items blank (don't force scores)

**Analysis Categories (from SampleCodeReview.xlsx):**
1. Code naming conventions / Code Structure (1, 1.1-1.6)
2. Reliability, Security & Observability (2, 2.1-2.4)
3. Delivery Discipline & Architecture (3, 3.1-3.4)
4. AI Usage & Code Ownership (4, 4.1-4.3)
5. Safe & Integrated AI Code (6, 6.1-6.3)

Each has sub-criteria scored 0-1, with:
- Average Points (mean of sub-scores)
- Final Points (calculated)
- % Points (percentage)
- Remarks (text explaining the score)

**Feature: Smart Detection**
- ✅ Test coverage: Auto-detect JaCoCo/Kover from gradle file
- ✅ Hardcoded secrets: Pattern matching (API keys, passwords, tokens)
- ✅ Gradle/SDK versions: Check against latest, warn if outdated
- ✅ Missing files: Flag but continue (hybrid error handling)

**Feature: Live Progress**
- Real-time updates: Ingest → Analysis → Scoring → Excel generation
- Stats dashboard: Show timing for each phase
- WebSocket or polling acceptable

**Feature: File Cleanup**
- Delete uploaded files immediately after review completes
- Temp directories cleaned up

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│  - Upload form (Android ZIP + Excel template)           │
│  - Progress tracker (live updates)                       │
│  - Download button                                       │
│  - Stats display (timing breakdown)                      │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/WebSocket
┌────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ 1. File Upload Handler                              ││
│  │    - Validate ZIP structure                         ││
│  │    - Validate Excel template (schema match)         ││
│  │    - Store in temp directory                        ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │ 2. Android Code Analyzer                            ││
│  │    - Extract key files (.java, .kt, gradle, etc)   ││
│  │    - Detect test coverage (JaCoCo/Kover)           ││
│  │    - Scan for hardcoded secrets                     ││
│  │    - Analyze Gradle/SDK versions                    ││
│  │    - Parse dependencies                             ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │ 3. Azure OpenAI Orchestrator                        ││
│  │    - Send code chunks to gpt-4o-mini               ││
│  │    - Use RAG-style prompts for each category       ││
│  │    - Extract scores & remarks                       ││
│  │    - Handle API errors gracefully                   ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │ 4. Excel Manipulator                                ││
│  │    - Load template (openpyxl)                       ││
│  │    - Preserve all formatting/styling                ││
│  │    - Populate scores & remarks                      ││
│  │    - Calculate totals & percentages                 ││
│  │    - Output new file                                ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │ 5. Progress Tracker                                 ││
│  │    - Track phase timings                            ││
│  │    - Send live updates to frontend                  ││
│  │    - Aggregate final stats                          ││
│  └─────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    Azure OpenAI          System Files
    (gpt-4o-mini)       (Temp uploads)
```

---

## 💻 Tech Stack

**Backend:**
- Framework: `fastapi` (async, modern)
- Async: `httpx` (for Azure OpenAI API calls)
- Excel: `openpyxl` (preserve formatting)
- ZIP: `zipfile` (built-in)
- Code parsing: `ast` (Python), regex (Java/Kotlin)
- Secrets scanning: `re` (pattern matching)
- Version checking: `packaging` library
- Logging: Built-in `logging`
- Temp files: `tempfile` + `shutil`

**Frontend:**
- Framework: React 18+
- HTTP: `axios` or `fetch` API
- Progress: `WebSocket` (for live updates) or polling via `/progress` endpoint
- UI: Tailwind CSS (or Material-UI, your choice)
- File upload: Native input + FormData

**Deployment:**
- Docker: Multi-stage build (Python 3.11 slim)
- Compose: frontend + backend services
- Volumes: For temp data (cleanup after)
- Environment: `.env` file with Azure OpenAI credentials

---

## 📐 Data Structures

### Request Payload (FormData)
```
POST /api/reviews
Content-Type: multipart/form-data

- androidZip: File (zip)
- excelTemplate: File (xlsx)
```

### Response Structure (WebSocket or polling)
```json
{
  "status": "processing|completed|error",
  "phase": "ingest|analysis|scoring|generation",
  "progress": 25,
  "message": "Extracting code files...",
  "stats": {
    "ingest_time_ms": 1200,
    "analysis_time_ms": 4500,
    "scoring_time_ms": 3200,
    "generation_time_ms": 800,
    "total_time_ms": 9700
  },
  "download_url": "/api/reviews/{review_id}/download",
  "error": null
}
```

### Analysis Result (internal)
```python
{
  "review_id": "uuid",
  "scores": {
    "1": {  # Category key
      "name": "Code naming conventions / Code Structure",
      "weight": 1,
      "sub_criteria": {
        "1.1": {"score": 1, "remark": "..."},
        "1.2": {"score": 1, "remark": "..."},
        "1.3": {"score": None, "remark": ""},  # Empty if not evaluated
        ...
      },
      "avg_points": 0.83,
      "final_points": 0.83,
      "percent": 83
    },
    ...
  },
  "warnings": [
    {"file": "build.gradle", "message": "Missing"},
    {"issue": "Gradle version 7.0 is outdated, latest is 8.1"}
  ],
  "test_coverage": 45,  # % if detected, None otherwise
  "secrets_found": [
    {"file": "Constants.java", "line": 42, "pattern": "api_key"}
  ]
}
```

---

## 🔌 API Endpoints

### 1. Upload & Analyze
```
POST /api/reviews
  - Body: FormData (androidZip, excelTemplate)
  - Returns: { review_id, status }
  - WebSocket: /ws/reviews/{review_id} for live progress
```

### 2. Get Progress (polling alternative)
```
GET /api/reviews/{review_id}/progress
  - Returns: { status, phase, progress, message, stats }
```

### 3. Download Result
```
GET /api/reviews/{review_id}/download
  - Returns: Binary (xlsx file)
  - Cleanup: File deleted after download
```

### 4. Health Check
```
GET /api/health
  - Returns: { status, azure_openai_connected }
```

---

## 🤖 Android Code Analysis Logic

### Phase 1: Ingest
1. Extract ZIP to temp directory
2. Validate structure (is it an Android project?)
3. List critical files:
   - `build.gradle` (or `build.gradle.kts`)
   - `AndroidManifest.xml`
   - `src/main/java/` or `src/main/kotlin/`
   - `src/test/`, `src/androidTest/`
   - Others: `.properties`, `.xml` configs
4. Flag missing files (don't fail, continue)

### Phase 2: Extract & Parse
- **Gradle file:**
  - Parse `android.compileSdkVersion`, `targetSdkVersion`
  - Extract plugin versions (gradle, kotlin, etc.)
  - List dependencies
  - Look for test plugins (jacoco, kover)

- **Source files:**
  - Count .java and .kt files
  - Parse package structure
  - Identify test files (JUnit patterns)
  - Scan for common naming violations

- **Test coverage:**
  - Look for JaCoCo config in build.gradle → search for `jacocoTestReport`, coverage XML
  - Look for Kover config → search for Kover gradle tasks
  - Try to locate coverage report files (XML/HTML)
  - If found, parse and extract percentage
  - If not found, estimate from test file count

- **Secrets scanning:**
  - Regex patterns for common secrets:
    - API keys: `api[_-]?key\s*=\s*["\']?[a-zA-Z0-9]{20,}["\']?` (case-insensitive)
    - AWS: `aws[_-]?secret|AKIAIOSFODNN7EXAMPLE`
    - Tokens: `token|secret|password` near strings with 20+ alphanumeric chars
    - Firebase: `"key":\s*"AIza[0-9a-zA-Z_\-]{35}"`
  - Report findings without failing

- **Version analysis:**
  - Extract SDK versions, Gradle version, Kotlin version
  - Compare against known latest versions (hardcode or fetch from maven central)
  - Warn if outdated (e.g., Gradle < 8.0, compileSdk < 33)

### Phase 3: Prepare for Analysis
- Chunk source code intelligently (max 8k tokens per chunk for Claude)
- Prioritize: exception handling patterns, logging, architecture, test structure
- Create analysis prompt with specific criteria

### Phase 4: Score Each Category

Use Azure OpenAI with system prompt:

```
You are an expert Android code reviewer. Analyze the provided code snippets
and score the following criteria on a scale of 0-1:

[Category description + sub-criteria]

For each sub-criterion, provide:
1. Score (0, 0.5, 1, or None if cannot evaluate)
2. Brief remark (1-2 sentences explaining the score)

If you cannot evaluate something (e.g., git history not available), leave score as null
and explanation as empty string.
```

**Scoring Rules:**
- 0 = Serious issues or missing
- 0.5 = Partial implementation or mixed quality
- 1 = Well implemented
- None = Cannot evaluate (leave empty)

**Example for Category 1 (Code naming conventions):**
```
Analyze the provided code for:
1.1 Clear and consistent naming conventions
1.2 Clean structure, formatting, and file organization
1.3 No unused, dead, or commented code
1.4 No compile-time warnings
1.5 No unused dependencies
1.6 Latest compile, target SDK, and gradle versions

[Provide code snippets here]

Score each criterion 0-1 and provide remarks.
```

---

## 📊 Excel Population Strategy

### Goal: Preserve Original Formatting

**Approach:**
1. Load template with `openpyxl` (read_only=False)
2. Locate each criterion cell by:
   - Row/column matching (row 1 = headers, row 2+ = data)
   - Or use named ranges if template has them
3. Populate without touching styling:
   - Use `worksheet.cell(row, col).value = score`
   - Don't modify font, color, border, shading
4. Calculate totals (if template has formulas, they auto-update)
5. Save to new file

**Critical:** Don't replace cells, only update values. Keep all original:
- Fonts, sizes, colors
- Borders, shading
- Merged cells
- Formulas (overwrite only data cells, not formula cells)

**Mapping (from SampleCodeReview.xlsx structure):**
- Headers in row 1
- Each category section:
  - Main category row (e.g., "1 Code naming conventions")
  - Sub-criteria rows (1.1, 1.2, ...)
  - Score columns: "Avg Points", "Final Points", "% Points", "Remarks"

Note: Extract the exact column indices from the template when loading.

---

## ⏱️ Performance Metrics

Track and display:
1. **Ingest time:** ZIP extraction + file validation
2. **Analysis time:** Code parsing + secret scanning + version checking
3. **Scoring time:** Azure OpenAI API calls for each category
4. **Generation time:** Excel population + file writing
5. **Total time:** Sum of all phases
6. **Tokens used:** (optional) from Azure OpenAI response

---

## 🔐 Azure OpenAI Integration

### Credentials (from .env)
```
OPENAI_API_BASE=https://norwayeast.api.cognitive.microsoft.com/
OPENAI_API_VERSION=2025-01-01-preview
OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
OPENAI_EMBEDDING_DEPLOYMENT=https://cloudrnd-foundry.cognitiveservices.azure.com/openai/deployments/text-embedding-3-small/embeddings?api-version=2023-05-15
AZURE_EMBEDDING_ENDPOINT=https://cloudrnd-foundry.cognitiveservices.azure.com/
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_KEY=<your-key>
```

### API Calls
- Use `httpx` async client
- Endpoint: `{OPENAI_API_BASE}/openai/deployments/{OPENAI_DEPLOYMENT_NAME}/chat/completions`
- Headers: `api-key: {AZURE_OPENAI_KEY}`
- Model: gpt-4o-mini (not model param, deployment controls it)
- Temperature: 0.3 (deterministic scoring)
- Max tokens: 1500 per call

### Error Handling
- Retry on rate limits (exponential backoff)
- Timeout: 30s per request
- Graceful degradation: If API fails, mark those criteria as "not evaluated"

---

## 🐳 Docker Setup

### Structure
```
android-code-review/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── reviews.py
│   │   ├── analyzer/
│   │   │   ├── __init__.py
│   │   │   ├── android_analyzer.py
│   │   │   ├── excel_handler.py
│   │   │   ├── openai_client.py
│   │   │   ├── secrets_scanner.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── logger.py
│   │       └── version_checker.py
│   ├── Dockerfile
│   └── .env
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UploadForm.jsx
│   │   │   ├── ProgressTracker.jsx
│   │   │   └── StatsDisplay.jsx
│   │   └── services/
│   │       └── api.js
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml
└── README.md
```

### Dockerfile (Backend)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (zipfile, git-related tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Run FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_BASE=${OPENAI_API_BASE}
      - OPENAI_API_VERSION=${OPENAI_API_VERSION}
      - OPENAI_DEPLOYMENT_NAME=${OPENAI_DEPLOYMENT_NAME}
      - AZURE_OPENAI_KEY=${AZURE_OPENAI_KEY}
    volumes:
      - /tmp/reviews:/tmp/reviews  # Temp files (cleanup after)
    networks:
      - review-network

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000/api
    depends_on:
      - backend
    networks:
      - review-network

networks:
  review-network:
    driver: bridge
```

### Run
```bash
docker-compose up -d
```

---

## 🧪 Development Workflow

### Local Setup (without Docker, for rapid iteration)
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

cd frontend
npm install
npm start
```

### Testing
- **Unit tests:** Test Android analyzer, secrets scanner, version checker
- **Integration tests:** Mock Azure OpenAI, test full pipeline
- **Manual:** Upload sample Android ZIP, verify Excel output

---

## 📝 Key Implementation Notes

1. **Excel Cell Mapping:**
   - Use `openpyxl.worksheet.worksheet.Worksheet.cell(row, col)` for safe access
   - Row indices start at 1 (not 0)
   - Don't assume column positions; parse headers dynamically

2. **Azure OpenAI Streaming (optional for future):**
   - Streaming can show live analysis updates
   - Use `stream=True` in httpx, parse Server-Sent Events (SSE)

3. **Temp File Cleanup:**
   - Use `tempfile.TemporaryDirectory()` context manager (auto-cleanup)
   - Or explicit shutil.rmtree() after download

4. **WebSocket Progress (vs Polling):**
   - WebSocket: `/ws/reviews/{review_id}`
   - Polling: `GET /api/reviews/{review_id}/progress` (easier, less infrastructure)
   - For POC, polling is fine

5. **Error Messages:**
   - Always send detailed errors to frontend
   - Don't expose Azure OpenAI API keys in error logs
   - Log to backend console, show user-friendly messages

6. **Gradle File Parsing:**
   - Use regex (simple cases) or groovy-style parsing
   - Look for `compileSdkVersion 33`, `targetSdkVersion 34`, etc.
   - Handle Kotlin DSL (build.gradle.kts) with same patterns

---

## 📦 Dependencies (Backend)

```
fastapi==0.104.1
uvicorn==0.24.0
httpx==0.25.0
openpyxl==3.11.0
python-multipart==0.0.6
python-dotenv==1.0.0
packaging==23.2
Pillow==10.0.0  # Optional: image processing for future
```

---

## 🚀 Deployment Checklist

- [ ] Env vars properly set (.env not committed)
- [ ] Docker build succeeds locally
- [ ] Frontend connects to backend correctly
- [ ] Sample Android ZIP upload works
- [ ] Sample Excel template loads without errors
- [ ] Azure OpenAI API responds
- [ ] File cleanup works (verify /tmp is clean)
- [ ] Progress updates show in real-time
- [ ] Download button triggers file download
- [ ] Stats display shows all timing metrics
- [ ] Error handling graceful (no blank page on failure)

---

## 🎓 Handover Notes

This document is complete enough for Claude Code to:
1. Understand the full architecture
2. Build backend (analyzer, API, integration)
3. Build frontend (upload, progress, download)
4. Create Docker setup
5. Implement error handling & logging
6. Test with sample data

**Questions for Claude Code:**
- Need sample Android project for testing?
- Should Kover detection also look for HTML reports?
- Polling interval preference (1s, 2s)?

---

## 📞 Support

For clarifications or changes:
- Reach out to Mehrosh
- Reference this document (section + line number)

---

**Generated:** July 23, 2026  
**Status:** Ready for Claude Code development
