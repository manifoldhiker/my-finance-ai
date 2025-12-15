#!/usr/bin/env python3
"""
Weekly Spending Report Generator

CLI script to generate spending reports from Monobank and Wise.
Uses the mcp.weekly_report module for report generation.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Add parent directory to path to import mcp module
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.weekly_report import generate_spending_report, fetch_all_transactions

VALID_BANKS = ["mono", "wise"]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate spending reports from Monobank and Wise."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Number of days to include in report (default: 14)"
    )
    parser.add_argument(
        "--banks",
        type=str,
        nargs="+",
        default=VALID_BANKS,
        choices=VALID_BANKS,
        help="Banks to fetch from (default: mono wise)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    # Load environment variables
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    
    args = parse_args()
    days = args.days
    banks = args.banks
    
    banks_str = ", ".join(banks)
    print(f"🔄 Generating spending report (last {days} days, banks: {banks_str})...")
    
    # Generate the report
    report = generate_spending_report(days=days, banks=banks)
    
    # Save report
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    banks_suffix = "_".join(sorted(banks))
    report_filename = f"spending_{datetime.now().strftime('%Y-%m-%d')}_{days}d_{banks_suffix}.md"
    report_path = reports_dir / report_filename
    
    report_path.write_text(report, encoding="utf-8")
    
    print(f"✅ Report saved to: {report_path}")
    print("")
    print("=" * 60)
    print(report)


if __name__ == "__main__":
    main()
