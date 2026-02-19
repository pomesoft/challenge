import argparse
import json
from pathlib import Path

from pipeline import EcosystemInput, run_pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", required=True)
    args = ap.parse_args()

    ecosystem_dict = json.loads(Path(args.ecosystem).read_text())
    ecosystem = EcosystemInput.model_validate(ecosystem_dict)

    result = run_pipeline(ecosystem)

    print("Session:", result.session_id)
    print("Report:\n")
    print(result.reporter.report_md if result.reporter else "No report generated")


if __name__ == "__main__":
    main()


