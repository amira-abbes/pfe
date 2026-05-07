from pathlib import Path

ELT_PROJECT_DIR = Path(r"C:\Users\benab\PycharmProjects\PythonProject1")
PLATFORM_PROJECT_DIR = Path(__file__).resolve().parents[3]

ELT_MAIN_FILE = ELT_PROJECT_DIR / "main_orchestrator.py"
ELT_WATCH_FILE = ELT_PROJECT_DIR / "local_watch_runner.py"

ELT_REPORTS_DIR = ELT_PROJECT_DIR / "reports"
ELT_PLATFORM_DATA_DIR = ELT_PROJECT_DIR / "platform_data"
PLATFORM_RUNTIME_DATA_DIR = PLATFORM_PROJECT_DIR / "backend" / "runtime_data"

ELT_LATEST_REPORT_FILE = ELT_PLATFORM_DATA_DIR / "latest_report.json"
ELT_WATCH_PROCESS_FILE = PLATFORM_RUNTIME_DATA_DIR / "watch_process.json"
ELT_LIVE_STATUS_FILE = ELT_PLATFORM_DATA_DIR / "live_status.json"
ELT_CURRENT_RUN_STATUS_FILE = ELT_PLATFORM_DATA_DIR / "current_run_status.json"
ELT_WATCHER_STATUS_FILE = ELT_PLATFORM_DATA_DIR / "watcher_status.json"
ELT_PYTHON_EXE = ELT_PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
TT_LOGO_FILE = PLATFORM_PROJECT_DIR / "frontend" / "public" / "tt-logo.png"
