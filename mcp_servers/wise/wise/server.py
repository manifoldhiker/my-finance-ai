from mcp.server.fastmcp import FastMCP
from .client import WiseClient
import os
from typing import List, Dict, Any

# Initialize FastMCP server
mcp = FastMCP("Wise")

def get_client() -> WiseClient:
    token = os.environ.get("WISE_API_TOKEN")
    if not token:
        raise RuntimeError("WISE_API_TOKEN not found in environment")
    return WiseClient(token=token)

@mcp.tool()
def get_profiles() -> List[Dict[str, Any]]:
    """
    List all Wise profiles (Personal, Business) associated with the token.
    """
    client = get_client()
    return client.get_profiles()

@mcp.tool()
def get_balances() -> List[Dict[str, Any]]:
    """
    Get balances (jars) for the default (or configured) profile.
    Returns list of accounts with currency and available amounts.
    """
    client = get_client()
    # Returns raw API response structure for borderless accounts
    return client.get_balances()

@mcp.tool()
def get_transactions(days: int = 30) -> List[Dict[str, Any]]:
    """
    Get transactions across ALL currency accounts for the last N days.
    Sorted by date descending.
    """
    client = get_client()
    return client.get_transactions(days=days)

if __name__ == "__main__":
    mcp.run()
