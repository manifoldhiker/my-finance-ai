"""
Weekly Spending Report Generator

Generates beautiful markdown reports from Monobank and Wise transactions.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Optional

from .monobank.client import MonobankClient
from .wise.client import WiseClient


def format_currency(amount: float, currency: str) -> str:
    """Format amount with currency symbol."""
    symbols = {"UAH": "₴", "USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł"}
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{amount:,.2f}"


def fetch_all_transactions(days: int = 14) -> List[Dict[str, Any]]:
    """
    Fetch transactions from all configured sources (Monobank + Wise).
    
    Returns:
        List of normalized transaction objects sorted by date descending.
    """
    all_txs = []
    
    # Fetch from Monobank
    try:
        mono_client = MonobankClient()
        monobank_txs = mono_client.get_all_transactions(days=days)
        mono_client.close()
        all_txs.extend(monobank_txs)
    except Exception as e:
        print(f"Monobank error: {e}")
    
    # Fetch from Wise
    try:
        wise_client = WiseClient()
        wise_txs = wise_client.get_all_transactions(days=days)
        wise_client.close()
        all_txs.extend(wise_txs)
    except Exception as e:
        print(f"Wise error: {e}")
    
    return sorted(all_txs, key=lambda x: x["date"], reverse=True)


def generate_report(all_txs: List[Dict[str, Any]], days: int = 14) -> str:
    """
    Generate a markdown spending report from normalized transactions.
    
    Args:
        all_txs: List of normalized transaction objects
        days: Number of days the report covers
        
    Returns:
        Markdown formatted report string
    """
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Separate expenses from income
    expenses = [tx for tx in all_txs if tx["is_expense"]]
    income = [tx for tx in all_txs if not tx["is_expense"]]
    
    # Calculate totals by currency
    expense_by_currency = defaultdict(float)
    for tx in expenses:
        expense_by_currency[tx["currency"]] += abs(tx["amount"])
    
    income_by_currency = defaultdict(float)
    for tx in income:
        income_by_currency[tx["currency"]] += abs(tx["amount"])
    
    # Expenses by category
    by_category = defaultdict(lambda: defaultdict(float))
    for tx in expenses:
        by_category[tx["currency"]][tx["category"]] += abs(tx["amount"])
    
    # Build report
    lines = []
    
    # Header
    period_name = "Weekly" if days <= 7 else f"{days}-Day"
    lines.append(f"# 📊 {period_name} Spending Report")
    lines.append("")
    lines.append(f"**Period:** {start_date.strftime('%B %d')} – {end_date.strftime('%B %d, %Y')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # ALL TRANSACTIONS LIST
    lines.append("## 📋 All Transactions")
    lines.append("")
    lines.append("| Date | Description | Amount | Category | Source |")
    lines.append("|:-----|:------------|-------:|:---------|:------:|")
    
    for tx in all_txs:
        date_str = tx["date"].strftime("%b %d %H:%M")
        desc = tx["description"][:40] + "..." if len(tx["description"]) > 40 else tx["description"]
        
        amt = tx["amount"]
        if amt < 0:
            amount_str = f"-{format_currency(abs(amt), tx['currency'])}"
        else:
            amount_str = f"+{format_currency(amt, tx['currency'])}"
        
        category = tx["category"]
        source_emoji = "🏦" if tx["source"] == "Monobank" else "🌍"
        acc_type = tx.get("account_type", "")
        source_label = f"{source_emoji} {acc_type}" if acc_type else tx["source"]
        
        lines.append(f"| {date_str} | {desc} | {amount_str} | {category} | {source_label} |")
    
    lines.append("")
    lines.append(f"*Total: {len(all_txs)} transactions ({len(expenses)} expenses, {len(income)} income)*")
    lines.append("")
    
    # Summary
    lines.append("---")
    lines.append("")
    lines.append("## 💰 Summary")
    lines.append("")
    lines.append("### Expenses")
    for currency in sorted(expense_by_currency.keys()):
        amount = expense_by_currency[currency]
        lines.append(f"- **{currency}**: {format_currency(amount, currency)}")
    
    if income_by_currency:
        lines.append("")
        lines.append("### Income")
        for currency in sorted(income_by_currency.keys()):
            amount = income_by_currency[currency]
            lines.append(f"- **{currency}**: +{format_currency(amount, currency)}")
    lines.append("")
    
    # Expenses by category (per currency)
    for currency in sorted(by_category.keys()):
        categories = by_category[currency]
        if not categories:
            continue
            
        total = sum(categories.values())
        
        lines.append("---")
        lines.append("")
        lines.append(f"## 📂 {currency} Expenses by Category")
        lines.append("")
        lines.append("| Category | Amount | % |")
        lines.append("|:---------|-------:|--:|")
        
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        for category, amount in sorted_cats:
            pct = (amount / total * 100) if total > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"| {category} | {format_currency(amount, currency)} | {pct:.0f}% {bar} |")
        
        lines.append(f"| **Total** | **{format_currency(total, currency)}** | |")
        lines.append("")
    
    # Top expenses
    if expenses:
        top_expenses = sorted(expenses, key=lambda x: abs(x["amount"]), reverse=True)[:10]
        
        lines.append("---")
        lines.append("")
        lines.append("## 🔝 Top 10 Expenses")
        lines.append("")
        lines.append("| # | Date | Description | Amount | Source |")
        lines.append("|:-:|:-----|:------------|-------:|:------:|")
        
        for i, tx in enumerate(top_expenses, 1):
            date_str = tx["date"].strftime("%b %d")
            desc = tx["description"][:35] + "..." if len(tx["description"]) > 35 else tx["description"]
            amount_str = format_currency(abs(tx["amount"]), tx["currency"])
            source_emoji = "🏦" if tx["source"] == "Monobank" else "🌍"
            lines.append(f"| {i} | {date_str} | {desc} | {amount_str} | {source_emoji} {tx['source']} |")
        lines.append("")
    
    # Daily breakdown
    daily = defaultdict(lambda: defaultdict(float))
    for tx in expenses:
        day = tx["date"].strftime("%a %d")
        daily[day][tx["currency"]] += abs(tx["amount"])
    
    if daily:
        lines.append("---")
        lines.append("")
        lines.append("## 📅 Daily Spending")
        lines.append("")
        
        all_currencies = set()
        for day_data in daily.values():
            all_currencies.update(day_data.keys())
        all_currencies = sorted(all_currencies)
        
        header = "| Day |" + " | ".join(all_currencies) + " |"
        separator = "|:----|" + "|".join(["-----:" for _ in all_currencies]) + "|"
        lines.append(header)
        lines.append(separator)
        
        current = start_date
        while current <= end_date:
            day = current.strftime("%a %d")
            row = f"| {day} |"
            for curr in all_currencies:
                amt = daily[day].get(curr, 0)
                if amt > 0:
                    row += f" {format_currency(amt, curr)} |"
                else:
                    row += " — |"
            lines.append(row)
            current += timedelta(days=1)
        lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    
    return "\n".join(lines)


def generate_spending_report(days: int = 14) -> str:
    """
    Generate a complete spending report for the given period.
    
    Fetches transactions from Monobank and Wise, then generates
    a comprehensive markdown report.
    
    Args:
        days: Number of days to include in the report (default: 14)
        
    Returns:
        Markdown formatted spending report
    """
    transactions = fetch_all_transactions(days=days)
    return generate_report(transactions, days=days)

