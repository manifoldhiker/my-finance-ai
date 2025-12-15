#!/usr/bin/env python3
"""
Weekly Spending Report Generator

CLI script to generate spending reports from Monobank and Wise.
Uses the mcp.weekly_report module for report generation.
"""

import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Add parent directory to path to import mcp module
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.weekly_report import generate_spending_report, fetch_all_transactions


def main():
    """Main entry point."""
    # Load environment variables
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    
    days = 14
    
    print(f"🔄 Generating spending report (last {days} days)...")
    
    # Generate the report
    report = generate_spending_report(days=days)
    
    # Save report
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    report_filename = f"spending_{datetime.now().strftime('%Y-%m-%d')}.md"
    report_path = reports_dir / report_filename
    
    report_path.write_text(report, encoding="utf-8")
    
    print(f"✅ Report saved to: {report_path}")
    print("")
    print("=" * 60)
    print(report)


if __name__ == "__main__":
    main()
