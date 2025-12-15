import os
import httpx
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

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
        
        # Auto-detect personal profile
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
        Get transactions for a borderless account (jar) or all accounts if not specified (conceptually).
        Wise API requires querying by borderless account ID.
        If borderless_account_id is None, it will fetch for ALL balances and merge.
        """
        pid = profile_id or self._get_profile_id()
        
        # If no specific account passed, get all valid accounts
        if not borderless_account_id:
            balances = self.get_balances(pid)
            all_txs = []
            for b_acc in balances:
                bid = b_acc.get("id")
                try:
                    txs = self._fetch_account_transactions(pid, bid, days)
                    # Enrich with currency/account info
                    for tx in txs:
                        tx["_account_currency"] = b_acc.get("currency")
                    all_txs.extend(txs)
                except Exception as e:
                    print(f"Failed to fetch transactions for account {bid}: {e}")
            
            # Sort by date desc
            return sorted(all_txs, key=lambda x: x.get("date", ""), reverse=True)
            
        return self._fetch_account_transactions(pid, borderless_account_id, days)

    def _fetch_account_transactions(self, profile_id: int, borderless_account_id: int, days: int) -> List[Dict[str, Any]]:
        """
        Internal helper to fetch statements for a specific jar.
        """
        now = datetime.now()
        start = now - timedelta(days=days)
        
        # Wise uses ISO strings
        params = {
            "intervalStart": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "intervalEnd": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "type": "COMPLETED" # Optional filter
        }
        
        url = f"/profiles/{profile_id}/borderless-accounts/{borderless_account_id}/statement.json"
        response = self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        return data.get("transactions", [])

    def close(self):
        self.client.close()
