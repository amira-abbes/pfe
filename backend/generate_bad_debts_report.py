import argparse
from datetime import datetime, timezone
from pathlib import Path

from app.db.database import SessionLocal
from app.services.bad_debts_llm_report_service import generate_global_llm_report
from app.services.bad_debts_pdf_service import generate_bad_debts_report
from app.services.bad_debts_service import BadDebtsService


def parse_args():
    parser = argparse.ArgumentParser(description="Génère un rapport PDF Bad Debts depuis les données réelles.")
    parser.add_argument("--output", default="rapport_bad_debts.pdf")
    parser.add_argument("--risk-tier", choices=["high", "medium", "low"])
    parser.add_argument("--cluster-name")
    parser.add_argument("--is-anomaly", choices=["true", "false"])
    parser.add_argument("--recommended-action")
    parser.add_argument("--search")
    return parser.parse_args()


def main():
    args = parse_args()
    filters = {
        "risk_tier": args.risk_tier,
        "cluster_name": args.cluster_name,
        "is_anomaly": None if args.is_anomaly is None else args.is_anomaly == "true",
        "recommended_action": args.recommended_action,
        "search": args.search,
    }
    db = SessionLocal()
    try:
        data = generate_global_llm_report(BadDebtsService(db), filters)
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        output = generate_bad_debts_report(data, Path(args.output))
        print(output.resolve())
    finally:
        db.close()


if __name__ == "__main__":
    main()
