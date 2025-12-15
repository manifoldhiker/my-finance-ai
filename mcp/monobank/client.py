import os
import time
import httpx
import monobank
import collections
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# Rate limit retry settings
RATE_LIMIT_WAIT_SECONDS = 61  # Monobank rate limit is 1 request per minute
INTER_ACCOUNT_DELAY = 5  # Small delay between accounts to be gentle on API
MAX_RETRIES = 3

# Currency code mapping
CURRENCY_MAP = {980: "UAH", 840: "USD", 978: "EUR", 826: "GBP", 985: "PLN"}

# MCC codes to human-readable categories
MCC_CATEGORIES = {
    "4111": "Transportation", "4112": "Railways", "4121": "Taxi & Rideshare",
    "4131": "Bus Lines", "4784": "Tolls & Fees", "4789": "Transportation Services",
    "4829": "Money Transfer", "5411": "Groceries", "5412": "Convenience Stores",
    "5422": "Meat & Seafood", "5441": "Candy & Confectionery", "5451": "Dairy Stores",
    "5462": "Bakeries", "5499": "Food Stores", "5541": "Gas Stations", "5542": "Fuel",
    "5651": "Clothing", "5691": "Clothing Stores", "5812": "Restaurants",
    "5813": "Bars & Nightclubs", "5814": "Fast Food", "5815": "Digital Goods",
    "5816": "Digital Games", "5817": "Digital Services", "5818": "Digital Purchases",
    "5912": "Pharmacy", "5921": "Alcohol", "5941": "Sporting Goods",
    "5942": "Bookstores", "5943": "Office Supplies", "5944": "Jewelry",
    "5945": "Toys & Games", "5977": "Cosmetics", "5999": "Retail",
    "6010": "ATM Cash", "6011": "Cash Withdrawal", "6012": "Financial Services",
    "6051": "Currency Exchange", "6211": "Investments", "6300": "Insurance",
    "7011": "Hotels", "7230": "Beauty Salons", "7299": "Other Services",
    "7372": "Software", "7375": "Information Services", "7379": "Computer Services",
    "7392": "Consulting", "7399": "Business Services", "7512": "Car Rental",
    "7523": "Parking", "7832": "Cinema", "7941": "Sports Events",
    "7999": "Recreation Services", "8011": "Medical", "8021": "Dentist",
    "8099": "Health Services", "8211": "Schools", "8299": "Education",
    "8398": "Charity", "9311": "Tax Payments", "9399": "Government Services",
}


def get_mcc_category(mcc: int) -> str:
    """Convert MCC code to human-readable category name."""
    return MCC_CATEGORIES.get(str(mcc), f"Other ({mcc})")


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
                txs = self.client.get_statements(account_id, current_start, current_end)
                all_txs.extend(txs)
            except Exception as e:
                if "429" in str(e):
                    print(f"Rate limit reached fetching transactions: {e}. Returning partial data.")
                    break
                elif "400" in str(e):
                     print(f"Date range invalid: {e}")
                     break
                else:
                    raise e
            
            current_start = current_end
            
        return all_txs

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """
        Get a simplified portfolio view: list of accounts with balance and currency.
        """
        info = self.get_client_info()
        accounts = []
        for acc in info.get("accounts", []):
            balance_raw = acc.get("balance", 0)
            currency_code = acc.get("currencyCode")
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
            if amount < 0:
                amount_abs = abs(amount) / 100.0
                mcc = str(tx.get("mcc", "Unknown"))
                
                by_mcc[mcc] += amount_abs
                total_expense += amount_abs
                
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
        groups = collections.defaultdict(list)
        
        for tx in transactions:
            amount = tx.get('amount', 0)
            desc = tx.get('description', '').strip()
            
            if amount < 0:
                amount_abs = abs(amount) / 100.0
                if amount_abs > 0:
                    groups[(desc, amount_abs)].append(tx)
        
        recurring = []
        for (desc, amount), txs in groups.items():
            if len(txs) > 1:
                times = sorted([tx.get('time') for tx in txs])
                intervals = []
                for i in range(1, len(times)):
                    intervals.append(times[i] - times[i-1])
                
                avg_interval_sec = sum(intervals) / len(intervals) if intervals else 0
                avg_interval_days = avg_interval_sec / (24 * 3600)
                
                recurring.append({
                    "description": desc,
                    "amount": amount,
                    "count": len(txs),
                    "avg_interval_days": round(avg_interval_days, 1),
                    "last_transaction": datetime.fromtimestamp(times[-1]).isoformat()
                })
        
        return sorted(recurring, key=lambda x: x['count'], reverse=True)

    def get_all_transactions(self, days: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch transactions from ALL accounts using direct HTTP calls.
        Returns normalized transaction objects with consistent structure.
        """
        headers = {"X-Token": self.token}
        now = datetime.now()
        start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        all_transactions = []
        
        with httpx.Client(base_url="https://api.monobank.ua", headers=headers, timeout=30.0) as client:
            info_response = client.get("/personal/client-info")
            info_response.raise_for_status()
            info = info_response.json()
            
            accounts = info.get("accounts", [])
            
            for idx, acc in enumerate(accounts):
                account_id = acc.get("id")
                currency_code = acc.get("currencyCode")
                currency = CURRENCY_MAP.get(currency_code, str(currency_code))
                acc_type = acc.get("type", "unknown")
                
                if acc_type == "fop" and acc.get("balance", 0) == 0:
                    continue
                
                # Small delay between accounts to be gentle on API
                if idx > 0:
                    time.sleep(INTER_ACCOUNT_DELAY)
                
                start_ts = int(start_date.timestamp())
                end_ts = int(now.timestamp())
                
                # Retry loop for rate limits
                for attempt in range(MAX_RETRIES):
                    try:
                        statement_response = client.get(f"/personal/statement/{account_id}/{start_ts}/{end_ts}")
                        statement_response.raise_for_status()
                        transactions = statement_response.json()
                        
                        if not isinstance(transactions, list):
                            break
                        
                        for tx in transactions:
                            tx_time = tx.get("time", 0)
                            tx_date = datetime.fromtimestamp(tx_time)
                            
                            if tx_date < start_date or tx_date > now:
                                continue
                            
                            amount = tx.get("amount", 0) / 100.0
                            mcc = tx.get("mcc", 0)
                            
                            all_transactions.append({
                                "date": tx_date,
                                "description": tx.get("description", "Unknown"),
                                "amount": amount,
                                "currency": currency,
                                "mcc": str(mcc),
                                "category": get_mcc_category(mcc),
                                "source": "Monobank",
                                "account_type": acc_type,
                                "is_expense": amount < 0
                            })
                        
                        # Success - break out of retry loop
                        break
                            
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            if attempt < MAX_RETRIES - 1:
                                wait_time = RATE_LIMIT_WAIT_SECONDS * (attempt + 1)
                                print(f"   ⏳ Rate limit hit for {acc_type}/{currency}. Waiting {wait_time}s before retry {attempt + 1}/{MAX_RETRIES}...")
                                time.sleep(wait_time)
                                continue
                            else:
                                print(f"   ⚠️  Rate limit hit for {acc_type}/{currency}. Max retries exceeded.")
                        else:
                            print(f"   ⚠️  Error fetching {acc_type}/{currency}: {e}")
                        break
                    except Exception as e:
                        print(f"   ⚠️  Error: {e}")
                        break
        
        return sorted(all_transactions, key=lambda x: x["date"], reverse=True)

    def close(self):
        pass

