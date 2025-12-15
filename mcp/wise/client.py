import os
import re
import httpx
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta


def parse_amount_string(amount_str: str) -> tuple[float, str]:
    """Parse amount string like '1.40 EUR' or '3,300 EUR' into (amount, currency)."""
    if not amount_str:
        return 0.0, "EUR"
    
    amount_str = amount_str.replace(",", "")
    parts = amount_str.strip().split()
    
    if len(parts) >= 2:
        try:
            amount = float(parts[0])
            currency = parts[1]
            return amount, currency
        except ValueError:
            pass
    
    return 0.0, "EUR"


class WiseClient:
    BASE_URL = "https://api.wise.com/v1"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("WISE_API_TOKEN")
        if not self.token:
            raise ValueError("Wise API token is required (WISE_API_TOKEN env var)")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers=self.headers,
            timeout=30.0
        )
        self._profile_id = os.environ.get("WISE_PROFILE_ID")

    def _get_profile_id(self) -> int:
        if self._profile_id:
            return int(self._profile_id)
        
        profiles = self.get_profiles()
        for p in profiles:
            if p.get("type") == "personal":
                self._profile_id = p.get("id")
                return self._profile_id
        
        if profiles:
            return profiles[0].get("id")
            
        raise ValueError("No Wise profiles found for this account")

    def get_profiles(self) -> List[Dict[str, Any]]:
        """List all profiles associated with the user."""
        response = self.client.get("/profiles")
        response.raise_for_status()
        return response.json()

    def get_balances(self, profile_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get account balances (jars) for a profile."""
        pid = profile_id or self._get_profile_id()
        response = self.client.get(f"/borderless-accounts?profileId={pid}")
        response.raise_for_status()
        return response.json()

    def get_transactions(self, profile_id: Optional[int] = None, borderless_account_id: Optional[int] = None, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get transactions for a borderless account (jar) or all accounts if not specified.
        """
        pid = profile_id or self._get_profile_id()
        
        if not borderless_account_id:
            balances = self.get_balances(pid)
            all_txs = []
            for b_acc in balances:
                bid = b_acc.get("id")
                try:
                    txs = self._fetch_account_transactions(pid, bid, days)
                    for tx in txs:
                        tx["_account_currency"] = b_acc.get("currency")
                    all_txs.extend(txs)
                except Exception as e:
                    print(f"Failed to fetch transactions for account {bid}: {e}")
            
            return sorted(all_txs, key=lambda x: x.get("date", ""), reverse=True)
            
        return self._fetch_account_transactions(pid, borderless_account_id, days)

    def _fetch_account_transactions(self, profile_id: int, borderless_account_id: int, days: int) -> List[Dict[str, Any]]:
        """Internal helper to fetch statements for a specific jar."""
        now = datetime.now()
        start = now - timedelta(days=days)
        
        params = {
            "intervalStart": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "intervalEnd": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "type": "COMPLETED"
        }
        
        url = f"/profiles/{profile_id}/borderless-accounts/{borderless_account_id}/statement.json"
        response = self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        txs = data.get("transactions", [])
        return txs

    def get_transfers(self, days: int = 14) -> List[Dict[str, Any]]:
        """Fetch bank transfers (outgoing payments) from Wise."""
        now = datetime.now()
        start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        response = self.client.get("/transfers", params={"limit": 200})
        response.raise_for_status()
        transfers = response.json()
        
        processed = []
        for tx in transfers:
            status = tx.get("status", "")
            if status not in ["outgoing_payment_sent", "funds_converted"]:
                continue
            
            created = tx.get("created", "")
            try:
                tx_date = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
            except:
                continue
            
            if tx_date < start_date or tx_date > now:
                continue
            
            source_value = tx.get("sourceValue", 0)
            source_currency = tx.get("sourceCurrency", "EUR")
            target_currency = tx.get("targetCurrency", "EUR")
            reference = tx.get("reference", "") or tx.get("details", {}).get("reference", "")
            
            # Check if this is an incoming transfer (sourceAccount is null = money coming IN)
            source_account = tx.get("sourceAccount")
            is_incoming = source_account is None
            
            if source_currency != target_currency:
                desc = f"{reference or 'Transfer'} ({source_currency}→{target_currency})"
            else:
                desc = reference or "Bank Transfer"
            
            processed.append({
                "date": tx_date,
                "description": desc,
                "amount": source_value if is_incoming else -source_value,
                "currency": source_currency,
                "mcc": None,
                "category": "Bank Transfer",
                "source": "Wise",
                "account_type": "transfer",
                "is_expense": not is_incoming
            })
        
        return sorted(processed, key=lambda x: x["date"], reverse=True)

    def get_card_transactions(self, days: int = 14) -> List[Dict[str, Any]]:
        """Fetch card transactions from Wise using the activities endpoint."""
        pid = self._get_profile_id()
        now = datetime.now()
        start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        processed = []
        cursor = None
        seen_ids = set()
        
        while True:
            params = {"size": 100}
            if cursor:
                params["cursor"] = cursor
            
            response = self.client.get(f"/profiles/{pid}/activities", params=params)
            response.raise_for_status()
            data = response.json()
            
            activities = data.get("activities", [])
            if not activities:
                break
            
            for act in activities:
                act_id = act.get("id")
                if act_id in seen_ids:
                    continue
                seen_ids.add(act_id)
                
                act_type = act.get("type", "")
                status = act.get("status", "")
                
                if act_type != "CARD_PAYMENT":
                    continue
                if status not in ["COMPLETED", "PENDING"]:
                    continue
                
                created = act.get("createdOn", "")
                try:
                    tx_date = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                except:
                    continue
                
                if tx_date < start_date:
                    break
                if tx_date > now:
                    continue
                
                primary_amount = act.get("primaryAmount", "")
                amount, currency = parse_amount_string(primary_amount)
                
                secondary = act.get("secondaryAmount", "")
                if secondary:
                    sec_amount, sec_currency = parse_amount_string(secondary)
                    if sec_amount > 0:
                        amount = sec_amount
                        currency = sec_currency
                
                title = act.get("title", "Unknown")
                title = re.sub(r'<[^>]+>', '', title).strip()
                
                category = self._categorize_merchant(title)
                
                processed.append({
                    "date": tx_date,
                    "description": title,
                    "amount": -amount,
                    "currency": currency,
                    "mcc": None,
                    "category": category,
                    "source": "Wise",
                    "account_type": "card",
                    "is_expense": True
                })
            
            if activities:
                last_created = activities[-1].get("createdOn", "")
                try:
                    last_date = datetime.fromisoformat(last_created.replace("Z", "+00:00")).replace(tzinfo=None)
                    if last_date < start_date:
                        break
                except:
                    pass
            
            cursor = data.get("cursor")
            if not cursor:
                break
        
        return sorted(processed, key=lambda x: x["date"], reverse=True)

    def _categorize_merchant(self, merchant: str) -> str:
        """Categorize merchant based on name."""
        merchant_lower = merchant.lower()
        
        if any(x in merchant_lower for x in ["uber", "bolt", "lyft", "taxi", "cabify"]):
            return "Transport"
        
        if any(x in merchant_lower for x in ["lidl", "aldi", "pingo doce", "continente", "mercado", "supermarket", "grocery"]):
            return "Groceries"
        
        if any(x in merchant_lower for x in ["restaurant", "cafe", "coffee", "starbucks", "mcdonald", "burger", "pizza", "sushi"]):
            return "Restaurants"
        
        if any(x in merchant_lower for x in ["patreon", "netflix", "spotify", "youtube", "apple", "google", "amazon prime"]):
            return "Subscriptions"
        
        if any(x in merchant_lower for x in ["pharmacy", "farmacia", "gym", "yoga", "fitness", "health"]):
            return "Health & Fitness"
        
        if any(x in merchant_lower for x in ["amazon", "ebay", "aliexpress", "shop", "store", "market"]):
            return "Shopping"
        
        return "Card Payment"

    def get_all_transactions(self, days: int = 14) -> List[Dict[str, Any]]:
        """Fetch ALL transactions from Wise (card payments + bank transfers)."""
        card_txs = self.get_card_transactions(days=days)
        transfer_txs = self.get_transfers(days=days)
        
        all_txs = card_txs + transfer_txs
        return sorted(all_txs, key=lambda x: x["date"], reverse=True)

    def close(self):
        self.client.close()

