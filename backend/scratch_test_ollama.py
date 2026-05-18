import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.bad_debts_llm_report_service import generate_global_llm_report
from app.services.bad_debts_service import BadDebtsService
from app.db.database import SessionLocal

def test_single_call():
    db = SessionLocal()
    try:
        service = BadDebtsService(db)
        payload = {"risk_tier": "high"}
        print(f"Testing generate_global_llm_report with {payload}")
        start = time.perf_counter()
        response = generate_global_llm_report(service, payload)
        elapsed = time.perf_counter() - start
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"Source: {response.get('report_source')}")
        if response.get('report_source') == "deterministic_fallback":
             print(f"Fallback reason: {response.get('report_generation', {}).get('fallback_reason')}")
        
        # print(json.dumps(response.get('report'), indent=2, ensure_ascii=False))
    finally:
        db.close()

if __name__ == "__main__":
    test_single_call()
