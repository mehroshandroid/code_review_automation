# Android Code Review Automation - Quick Reference

## 📊 Review Scoring Structure

| Category | Weight | Sub-criteria | Score Range |
|----------|--------|--------------|-------------|
| 1. Code naming conventions / Code Structure | 1 | 1.1-1.6 (6 items) | 0-1 |
| 2. Reliability, Security & Observability | 1 | 2.1-2.4 (4 items) | 0-1 |
| 3. Delivery Discipline & Architecture | 1 | 3.1-3.4 (4 items) | 0-1 |
| 4. AI Usage & Code Ownership | 1 | 4.1-4.3 (3 items) | 0-1 |
| 5. Safe & Integrated AI Code | 1 | 6.1-6.3 (3 items) | 0-1 |

**Calculations:**
- `Avg Points` = Mean of sub-criteria scores
- `Final Points` = Avg Points × Weight
- `% Points` = (Final Points / max possible) × 100
- `Total %` = (Sum of all Final Points / sum of weights) × 100

---

## 🛠️ Tech Stack Summary

| Layer | Tech |
|-------|------|
| Backend | Python 3.11 + FastAPI + async httpx |
| Frontend | React 18+ + Axios + Tailwind CSS |
| Excel | openpyxl (preserve formatting) |
| Code parsing | ast (Python), regex (Java/Kotlin/Gradle) |
| AI | Azure OpenAI (gpt-4o-mini) |
| Deployment | Docker + docker-compose |
| Secrets scanning | Regex patterns (no external tools) |
| Version checking | packaging library |

---

## 📡 API Endpoints

```
POST   /api/reviews                    Upload Android ZIP + Excel template
GET    /api/reviews/{id}/progress      Poll for progress updates
GET    /api/reviews/{id}/download      Download populated Excel
GET    /api/health                     Health check
WS     /ws/reviews/{id}                WebSocket for live updates (optional)
```

---

## 🔍 Detection Features

### Test Coverage
- **Look for:** JaCoCo XML reports, Kover gradle config
- **Parse:** `build.gradle` for test plugins
- **Locate:** Coverage report files (usually `build/reports/jacoco/`)
- **Fallback:** Estimate from test file count if report not found

### Hardcoded Secrets
- **Patterns:** API keys, AWS secrets, tokens, Firebase keys
- **Regex:** Match `api[_-]?key`, `aws[_-]?secret`, `token`, etc.
- **Range:** Alphanumeric strings 20+ chars near string literals
- **Report:** List file + line number for each finding

### Gradle/SDK Versions
- **Extract:** `compileSdkVersion`, `targetSdkVersion`, Gradle version, Kotlin version
- **Compare:** Against hardcoded latest versions (or can fetch from Maven Central)
- **Action:** Warn if outdated, don't fail review
- **Update:** Gradle 8.0+, compileSdk 33+, Kotlin 1.8+

---

## 🔐 Azure OpenAI Setup

**Credentials (in .env):**
```
OPENAI_API_BASE=https://norwayeast.api.cognitive.microsoft.com/
OPENAI_API_VERSION=2025-01-01-preview
OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_KEY=<your-api-key>
```

**API Call Pattern:**
```
POST {OPENAI_API_BASE}/openai/deployments/{OPENAI_DEPLOYMENT_NAME}/chat/completions
Header: api-key: {AZURE_OPENAI_KEY}
Body: {
  "messages": [...],
  "temperature": 0.3,
  "max_tokens": 1500
}
```

**Timeout:** 30 seconds per request  
**Retry:** Exponential backoff on rate limits

---

## 📁 Project Structure

```
android-code-review/
├── backend/
│   ├── main.py                    # FastAPI app entry
│   ├── requirements.txt
│   ├── app/
│   │   ├── api/
│   │   │   └── reviews.py         # Endpoints
│   │   ├── analyzer/
│   │   │   ├── android_analyzer.py    # Extract code structure
│   │   │   ├── excel_handler.py       # Load/save templates
│   │   │   ├── openai_client.py       # Score via Azure OpenAI
│   │   │   └── secrets_scanner.py     # Find hardcoded secrets
│   │   └── utils/
│   │       ├── logger.py          # Structured logging
│   │       └── version_checker.py # Check SDK/Gradle versions
│   ├── Dockerfile
│   └── .env
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UploadForm.jsx     # File input
│   │   │   ├── ProgressTracker.jsx    # Live updates
│   │   │   └── StatsDisplay.jsx       # Timing metrics
│   │   └── services/
│   │       └── api.js             # HTTP client
│   └── Dockerfile
└── docker-compose.yml             # Start both services
```

---

## ⏱️ Performance Tracking

**Metrics to capture:**
1. `ingest_time_ms` - ZIP extraction + validation
2. `analysis_time_ms` - Code parsing + secret scan + version check
3. `scoring_time_ms` - Azure OpenAI API calls (per category)
4. `generation_time_ms` - Excel population
5. `total_time_ms` - Sum of all

**Display on frontend** after completion.

---

## 🚦 Progress States

```
1. pending       → Waiting to start
2. extracting    → Unzipping + validating files
3. analyzing     → Parsing code + scanning secrets
4. scoring       → Calling Azure OpenAI for each category
5. generating    → Populating Excel
6. completed     → Ready to download
7. error         → Failed (show error message)
```

---

## 💾 Excel Handling

**Key Rules:**
- Load template with `openpyxl` (read_only=False)
- Update cell values ONLY, don't touch formatting
- Preserve: fonts, colors, borders, merged cells, formulas
- Map by row/column indices (extract from template headers)
- Calculate totals after all scores populated
- Save to new file with original template structure intact

**Example:**
```python
from openpyxl import load_workbook

wb = load_workbook('template.xlsx')
ws = wb.active

# Update only values, preserve styling
ws['C5'].value = 0.83  # Score
ws['F5'].value = "Clear naming conventions found"  # Remark

wb.save('output.xlsx')
```

---

## 🔄 Error Handling Strategy

**Non-fatal errors (continue analysis):**
- Missing build.gradle → Flag warning, continue
- No test files → Set coverage to None, mark unavailable
- Gradle version parse fails → Warn, set to None
- Azure OpenAI timeout → Mark category as "not evaluated"

**Fatal errors (stop immediately):**
- Invalid ZIP structure
- Invalid Excel template (schema mismatch)
- No source files found (.java/.kt)

**User feedback:**
- Always return HTTP 200 with error details
- Store errors in response: `{ "status": "error", "message": "...", "phase": "..." }`
- Frontend shows error message clearly

---

## 🧹 Cleanup Strategy

**After review completes:**
1. Delete uploaded ZIP file
2. Delete Excel template copy
3. Delete temp extraction directory
4. Keep output Excel (until downloaded)
5. Delete output Excel after download completes (or after 1 hour)

**Implementation:**
```python
import tempfile
import shutil

with tempfile.TemporaryDirectory() as tmpdir:
    # Extract, analyze, generate
    # Auto-cleanup when context exits
```

---

## 🎯 Scoring Examples

### Category 1.1 (Clear and consistent naming conventions)
**Score 1:** All classes, methods, variables follow camelCase/PascalCase conventions consistently  
**Score 0.5:** Most follow conventions with some violations (10-20%)  
**Score 0:** Many inconsistencies or no convention (20%+ violations)  
**None:** Cannot evaluate (insufficient code samples)

### Category 2.1 (Proper exception handling)
**Score 1:** All exceptions caught, logged properly, user informed  
**Score 0.5:** Exceptions handled inconsistently (some catch-all, some proper)  
**Score 0:** No/minimal exception handling, stack traces printed  
**None:** No exception-prone code found

---

## 🚀 Running Locally

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=<key>
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm start

# Access: http://localhost:3000
```

---

## 🐳 Running via Docker

```bash
# Build & run
docker-compose up -d

# Logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop
docker-compose down

# Access: http://localhost:3000
```

---

## 📋 Pre-delivery Checklist

- [ ] All env vars properly set in .env
- [ ] Docker images build without errors
- [ ] Frontend connects to backend
- [ ] Sample Android ZIP uploads successfully
- [ ] Excel template validates correctly
- [ ] Azure OpenAI credentials work
- [ ] File cleanup verified (check /tmp)
- [ ] Progress updates render live
- [ ] Download triggers file save
- [ ] Stats show all timing breakdowns
- [ ] Error states handled gracefully
- [ ] Logs are structured and useful
- [ ] No sensitive data in logs/errors
- [ ] Code comments for complex logic

---

**For detailed implementation guidance, see: HANDOVER_ANDROID_CODE_REVIEW.md**
