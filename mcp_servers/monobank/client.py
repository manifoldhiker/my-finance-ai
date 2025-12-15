import os
import monobank
import collections
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

class MonobankClient:
    """
    Higher-level wrapper around the official python-monobank client.
    """
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("MONOBANK_API_TOKEN")
        if not self.token:
            raise ValueError("Monobank API token is required (MONOBANK_API_TOKEN env var)")
        
        self.client = monobank.Client(self.token)

    def get_client_info(self) -> Dict[str, Any]:
        """Retrieve raw client info."""
        return self.client.get_client_info()

    def get_transactions(self, account_id: str = "0", days: int = 30) -> List[Dict[str, Any]]:
        """
        Retrieve statement for a specific time range.
        Automatically chunks requests if days > 30.
        """
        now = datetime.now()
        start_date = now - timedelta(days=days)
        all_txs = []
        
        # Chunk into 30-day intervals
        current_start = start_date
        while current_start < now:
            current_end = current_start + timedelta(days=30)
            if current_end > now:
                current_end = now
                
            # Fetch chunk
            try:
                # Note: Monobank API rate limit is 1 req/60s. 
                # If we make multiple requests, we might hit 429.
                # We'll validly handle the time range limit (31 days) first.
                txs = self.client.get_statements(account_id, current_start, current_end)
                all_txs.extend(txs)
            except Exception as e:
                # If we hit an error (like 429), log/print and break to return partial data
                # Ideally check for "Too Many Requests"
                if "429" in str(e):
                    print(f"Rate limit reached fetching transactions: {e}. Returning partial data.")
                    break
                elif "400" in str(e): # Limit exceeded?
                     print(f"Date range invalid: {e}")
                     break
                else:
                    raise e
            
            # Move to next chunk
            current_start = current_end
            
            # Simple dedup if needed (endpoints match?), but usually time logic checks out.
            
        return all_txs

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """
        Get a simplified portfolio view: list of accounts with balance and currency.
        """
        info = self.get_client_info()
        accounts = []
        for acc in info.get("accounts", []):
            # Balance is in cents
            balance_raw = acc.get("balance", 0)
            currency_code = acc.get("currencyCode")
            
            # Simple currency mapping (common ones)
            currency = {980: "UAH", 840: "USD", 978: "EUR"}.get(currency_code, str(currency_code))
            
            accounts.append({
                "id": acc.get("id"),
                "type": acc.get("type"),
                "currency": currency,
                "balance": balance_raw / 100.0,
                "credit_limit": acc.get("creditLimit", 0) / 100.0,
                "cashback_type": acc.get("cashbackType")
            })
        return accounts

    def get_expense_stats(self, account_id: str = "0", days: int = 30) -> Dict[str, Any]:
        """
        Get spending statistics: total spent, and breakdown by Category (MCC).
        """
        txs = self.get_transactions(account_id, days)
        by_mcc = collections.defaultdict(float)
        
        total_expense = 0.0
        
        for tx in txs:
            amount = tx.get("amount", 0)
            # Filter for expenses (negative amount) and ignore transfers if possible?
            # Monobank doesn't explicitly flag transfers easily without MCC parsing, 
            # but usually MCC 4829 is transfer.
            if amount < 0:
                amount_abs = abs(amount) / 100.0
                mcc = str(tx.get("mcc", "Unknown"))
                
                by_mcc[mcc] += amount_abs
                total_expense += amount_abs
                
        # Sort MCCs by spend
        sorted_mcc = dict(sorted(by_mcc.items(), key=lambda i: i[1], reverse=True))
        
        return {
            "period_days": days,
            "total_spent": round(total_expense, 2),
            "by_category": {k: round(v, 2) for k, v in sorted_mcc.items()}
        }

    def detect_recurring_payments(self, account_id: str = "0", days: int = 90) -> List[Dict[str, Any]]:
        """
        Identify potential subscriptions based on repeated transaction descriptions and amounts.
        """
        transactions = self.get_transactions(account_id, days)
        
        # Group by (description, abs(amount))
        # Subscription is usually same amount + same vendor
        groups = collections.defaultdict(list)
        
        for tx in transactions:
            amount = tx.get('amount', 0)
            desc = tx.get('description', '').strip()
            
            if amount < 0: # Only expenses
                amount_abs = abs(amount) / 100.0
                if amount_abs > 0:
                    groups[(desc, amount_abs)].append(tx)
        
        recurring = []
        for (desc, amount), txs in groups.items():
            if len(txs) > 1:
                # Calculate intervals
                times = sorted([tx.get('time') for tx in txs])
                intervals = []
                for i in range(1, len(times)):
                    intervals.append(times[i] - times[i-1])
                
                avg_interval_sec = sum(intervals) / len(intervals) if intervals else 0
                avg_interval_days = avg_interval_sec / (24 * 3600)
                
                # Heuristic: Recurring if interval is roughly 7, 30, or 365 days
                # But we'll just return anything that repeats > 1 time in 90 days for the agent to decide.
                
                
                recurring.append({
                    "description": desc,
                    "amount": amount,
                    "count": len(txs),
                    "avg_interval_days": round(avg_interval_days, 1),
                    "last_transaction": datetime.fromtimestamp(times[-1]).isoformat()
                })
        
        # Sort by count desc
        return sorted(recurring, key=lambda x: x['count'], reverse=True)

    def close(self):
        # Result of no-op for sync client
        pass
