# Gmail Cleanup Tool

A desktop tool that classifies your unread Gmail emails as **Important** or **Low Priority** using a local Ollama LLM. Emails are labeled directly in Gmail and a summary report is generated. Everything runs locally — no email content leaves your machine.

## Prerequisites

- **Python 3.10+**
- **Ollama** installed and running locally ([ollama.com](https://ollama.com))
- A **Google Cloud project** with the Gmail API enabled
- **pystray** and **Pillow** (included in `requirements.txt`) for system tray support

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Pull the Ollama Model

Make sure Ollama is running, then pull the model:

```bash
ollama pull qwen2.5-coder:14b
```

You can substitute a different model by editing `OLLAMA_MODEL` in `config.py`.

### 3. Set Up Gmail API Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Gmail API** (APIs & Services > Library > search "Gmail API" > Enable)
4. Configure the **OAuth consent screen** (APIs & Services > OAuth consent screen):
   - Choose "External" user type
   - Add your email as a test user
5. Create **OAuth credentials** (APIs & Services > Credentials > Create Credentials > OAuth client ID):
   - Application type: **Desktop app**
   - Download the JSON file
6. Save the downloaded file as `credentials/client_secret.json` in the project directory

## Running the Tool

```bash
python main.py
```

On first run, a browser window will open asking you to sign in to your Google account and grant Gmail access. The resulting token is saved to `credentials/token.json` so you won't need to re-authenticate on future runs.

## Using the GUI

| Control | Description |
|---------|-------------|
| **Query** | Gmail search query to select which emails to process (default: `is:unread`) |
| **Ollama URL** | Address of your Ollama instance (default: `http://localhost:11434`) |
| **Connected** | Shows the authenticated Gmail address after starting a run |
| **Start** | Begins a fresh classification run |
| **Stop** | Pauses the run and saves a checkpoint |
| **Resume** | Continues from the last saved checkpoint |
| **Dark Mode** | Toggles between light and dark themes |

The progress bar, counters, and log area show real-time status as emails are classified.

### Settings Persistence

Your query, Ollama URL, dark mode preference, and window position are saved automatically to `settings.json` when the application exits and restored on the next launch.

### System Tray

When you close the window, the application minimizes to the system tray instead of exiting. Double-click the tray icon to restore the window, or right-click and select **Exit** to quit. The tray icon requires the `pystray` and `Pillow` packages; if they are not installed, closing the window will exit the application normally.

## What It Does

1. Fetches all emails matching your query from Gmail
2. Sends each email's **From**, **Subject**, and **snippet** (no full body) to the local LLM
3. The LLM classifies each email as Important or Unimportant
4. Applies Gmail labels: `AI/Important` or `AI/Low Priority`
5. Generates an HTML report in the `output/` directory

Unrecognized LLM responses default to **Important** so nothing gets accidentally buried.

## Checkpoint & Resume

Progress is saved to `output/checkpoint.json` every 10 emails. If you stop the tool or it's interrupted, click **Resume** to pick up where you left off. The checkpoint is cleared automatically after a successful run.

## Performance

LLM classification is the bottleneck. The tool parallelizes it with a configurable number of concurrent workers (`LLM_WORKERS` in `config.py`, default 4). Email metadata is prefetched in the background so the next batch is ready as soon as classification finishes, and HTTP connections to Ollama are reused across requests.

For ~5,000 emails:

| Phase | Approximate Time |
|-------|-----------------|
| Fetch message IDs | ~5 seconds |
| Fetch email metadata | ~2 minutes |
| LLM classification | 10 min – 40 min (4 workers) |
| Apply labels | ~30 seconds |

Actual classification speed depends on your GPU and the number of workers. If Ollama can serve multiple requests in parallel (e.g. with `OLLAMA_NUM_PARALLEL`), increasing `LLM_WORKERS` will improve throughput further.

## Project Structure

```
gmail-cleanup/
├── main.py                # Entry point
├── config.py              # Constants and settings
├── gmail_auth.py          # OAuth2 authentication
├── gmail_client.py        # Gmail API interactions (fetch, label)
├── llm_classifier.py      # Ollama LLM classification
├── classifier_engine.py   # Orchestrator (runs in background thread)
├── gui.py                 # Tkinter GUI
├── state.py               # Checkpoint/resume persistence
├── requirements.txt       # Python dependencies
├── credentials/           # OAuth files (git-ignored)
├── output/                # Reports and checkpoint (git-ignored)
└── tests/                 # Unit tests
    ├── conftest.py        # Shared fixtures
    ├── test_state.py
    ├── test_gmail_auth.py
    ├── test_gmail_client.py
    ├── test_llm_classifier.py
    └── test_classifier_engine.py
```

## Running Tests

Install test dependencies:

```bash
pip install -r requirements.txt
```

Run the full test suite:

```bash
python -m pytest tests/ -v
```

All 38 tests are fully mocked — no Gmail API calls, Ollama requests, or filesystem side effects. The suite covers:

| Module | Tests | What's covered |
|--------|-------|----------------|
| `state.py` | 8 | Save/load round-trips, atomic writes, backward compatibility, clear |
| `gmail_auth.py` | 5 | Token loading, refresh, browser flow, missing credentials |
| `gmail_client.py` | 8 | Message fetching, pagination, batch details, label management |
| `llm_classifier.py` | 10 | Ollama availability, classification responses, error handling, timeouts |
| `classifier_engine.py` | 6 | Full pipeline, resume/checkpoint, stop event, report generation |
