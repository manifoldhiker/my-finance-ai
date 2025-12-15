from mcp.server.fastmcp import FastMCP
from .client import MonobankClient
import os
from typing import List, Dict, Any

# Initialize FastMCP server
mcp = FastMCP("Monobank")

def get_client() -> MonobankClient:
    token = os.environ.get("MONOBANK_API_TOKEN")
    if not token:
        raise RuntimeError("MONOBANK_API_TOKEN not found in environment")
    return MonobankClient(token=token)

@mcp.tool()
def get_client_info() -> Dict[str, Any]:
    """
    Get detailed information about the client and their accounts.
    Returns:
        JSON object with client name, permissions, and list of accounts.
    """
    client = get_client()
    return client.get_client_info()

@mcp.tool()
def get_transactions(account_id: str = "0", days: int = 30) -> List[Dict[str, Any]]:
    """
    Get bank transactions for a specific account over a number of days.
    
    Args:
        account_id: The account ID to fetch statements for (default: "0" for main currency account).
        days: Number of past days to fetch (max 30-31 recommended). Default 30.
    Returns:
        List of transaction objects.
    """
    client = get_client()
    return client.get_transactions(account_id=account_id, days=days)

@mcp.tool()
def get_portfolio() -> List[Dict[str, Any]]:
    """
    Get a simplified portfolio view: list of accounts with balance and currency.
    """
    client = get_client()
    return client.get_portfolio()

@mcp.tool()
def get_expense_stats(account_id: str = "0", days: int = 30) -> Dict[str, Any]:
    """
    Get spending statistics: total spent, and breakdown by Category (MCC).
    Returns a dictionary with 'total_spent' and 'by_category'.
    """
    client = get_client()
    return client.get_expense_stats(account_id=account_id, days=days)

@mcp.tool()
def detect_recurring_payments(account_id: str = "0", days: int = 90) -> List[Dict[str, Any]]:
    """
    Identify potential subscriptions based on repeated transaction amounts and descriptions.
    """
    client = get_client()
    return client.detect_recurring_payments(account_id=account_id, days=days)

if __name__ == "__main__":
    mcp.run()
