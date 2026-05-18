import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.bad_debts_llm_report_service import build_global_decision_context, _global_report_prompt
from app.services.bad_debts_service import BadDebtsService
from app.db.database import SessionLocal

def test_prompt():
    db = SessionLocal()
    try:
        service = BadDebtsService(db)
        payload = {"risk_tier": "high"}
        kpis = service.compute_global_kpis(risk_tier="high")
        active_filters = {"risk_tier": "high"}
        decision_context = build_global_decision_context(kpis, active_filters)
        prompt = _global_report_prompt(kpis, active_filters, decision_context)
        print(f"Prompt length: {len(prompt)} characters")
        print("--- PROMPT START ---")
        print(prompt)
        print("--- PROMPT END ---")
    finally:
        db.close()

if __name__ == "__main__":
    test_prompt()
