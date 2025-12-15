"""
Unified Financial MCP Server

Combines tools from Monobank and Wise into a single MCP server.
Tools are prefixed with 'monobank_' or 'wise_' to avoid naming conflicts.

Authentication:
    Set MCP_AUTH_TOKEN environment variable to enable Bearer token authentication.
    Clients must include header: Authorization: Bearer <token>
"""
import os
import time
import secrets
import functools
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP

from .monobank.client import MonobankClient
from .wise.client import WiseClient
from .weekly_report import generate_spending_report

# Initialize unified FastMCP server
mcp = FastMCP("Financial")

# Authentication token (set via environment variable)
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")


# ============================================================================
# Client Factories
# ============================================================================

def get_monobank_client() -> MonobankClient:
    token = os.environ.get("MONOBANK_API_TOKEN")
    if not token:
        raise RuntimeError("MONOBANK_API_TOKEN not found in environment")
    return MonobankClient(token=token)


def get_wise_client() -> WiseClient:
    token = os.environ.get("WISE_API_TOKEN")
    if not token:
        raise RuntimeError("WISE_API_TOKEN not found in environment")
    return WiseClient(token=token)


# ============================================================================
# Utilities
# ============================================================================

def rate_limit_retry(retries: int = 3, initial_delay: int = 5):
    """
    Decorator to retry function call if a 429 Rate Limit error is encountered.
    Uses exponential backoff (delay * 2).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Too Many Requests" in error_str:
                        if attempt < retries - 1:
                            print(f"Rate limit hit in {func.__name__}. Waiting {delay}s before retry {attempt + 1}/{retries}...")
                            time.sleep(delay)
                            delay *= 2
                            continue
                    raise e
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# Monobank Tools
# ============================================================================

@mcp.tool()
@rate_limit_retry()
def monobank_get_client_info() -> Dict[str, Any]:
    """
    [Monobank] Get detailed information about the client and their accounts.
    Returns:
        JSON object with client name, permissions, and list of accounts.
    """
    client = get_monobank_client()
    return client.get_client_info()


@mcp.tool()
@rate_limit_retry()
def monobank_get_transactions(account_id: str = "0", days: int = 30) -> List[Dict[str, Any]]:
    """
    [Monobank] Get bank transactions for a specific account over a number of days.
    
    Args:
        account_id: The account ID to fetch statements for (default: "0" for main currency account).
        days: Number of past days to fetch (max 30-31 recommended). Default 30.
    Returns:
        List of transaction objects.
    """
    client = get_monobank_client()
    return client.get_transactions(account_id=account_id, days=days)


@mcp.tool()
@rate_limit_retry()
def monobank_get_portfolio() -> List[Dict[str, Any]]:
    """
    [Monobank] Get a simplified portfolio view: list of accounts with balance and currency.
    """
    client = get_monobank_client()
    return client.get_portfolio()


@mcp.tool()
@rate_limit_retry()
def monobank_get_expense_stats(account_id: str = "0", days: int = 30) -> Dict[str, Any]:
    """
    [Monobank] Get spending statistics: total spent, and breakdown by Category (MCC).
    Returns a dictionary with 'total_spent' and 'by_category'.
    """
    client = get_monobank_client()
    return client.get_expense_stats(account_id=account_id, days=days)


@mcp.tool()
@rate_limit_retry()
def monobank_detect_recurring_payments(account_id: str = "0", days: int = 90) -> List[Dict[str, Any]]:
    """
    [Monobank] Identify potential subscriptions based on repeated transaction amounts and descriptions.
    """
    client = get_monobank_client()
    return client.detect_recurring_payments(account_id=account_id, days=days)


# ============================================================================
# Wise Tools
# ============================================================================

@mcp.tool()
def wise_get_profiles() -> List[Dict[str, Any]]:
    """
    [Wise] List all Wise profiles (Personal, Business) associated with the token.
    """
    client = get_wise_client()
    return client.get_profiles()


@mcp.tool()
def wise_get_balances() -> List[Dict[str, Any]]:
    """
    [Wise] Get balances (jars) for the default (or configured) profile.
    Returns list of accounts with currency and available amounts.
    """
    client = get_wise_client()
    return client.get_balances()


@mcp.tool()
def wise_get_transactions(days: int = 30) -> List[Dict[str, Any]]:
    """
    [Wise] Get transactions across ALL currency accounts for the last N days.
    Sorted by date descending.
    """
    client = get_wise_client()
    return client.get_transactions(days=days)


# ============================================================================
# Report Tools
# ============================================================================

@mcp.tool()
@rate_limit_retry()
def generate_report(days: int = 14) -> str:
    """
    Generate a comprehensive spending report combining Monobank and Wise transactions.
    
    Args:
        days: Number of days to include in the report (default: 14).
              Use 7 for weekly, 14 for bi-weekly, 30 for monthly.
    
    Returns:
        A beautifully formatted markdown report containing:
        - All transactions table
        - Summary of expenses and income by currency
        - Breakdown by category with percentages
        - Top 10 largest expenses
        - Daily spending breakdown
    """
    return generate_spending_report(days=days)


# ============================================================================
# SSE Server
# ============================================================================

def create_sse_app():
    """Create the SSE application for use with uvicorn."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import Response, JSONResponse
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        """Middleware to enforce Bearer token authentication."""
        
        async def dispatch(self, request: Request, call_next):
            # Skip auth if no token is configured
            if not MCP_AUTH_TOKEN:
                return await call_next(request)
            
            # Get Authorization header
            auth_header = request.headers.get("Authorization", "")
            
            # Check for Bearer token
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    {"error": "Missing or invalid Authorization header. Expected: Bearer <token>"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Extract and validate token (constant-time comparison to prevent timing attacks)
            provided_token = auth_header[7:]  # Remove "Bearer " prefix
            if not secrets.compare_digest(provided_token, MCP_AUTH_TOKEN):
                return JSONResponse(
                    {"error": "Invalid authentication token"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            return await call_next(request)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1], mcp._mcp_server.create_initialization_options()
            )
        # Must return Response to avoid NoneType error on client disconnect
        return Response()

    # Build middleware list
    middleware = [Middleware(BearerAuthMiddleware)]

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        middleware=middleware
    )


if __name__ == "__main__":
    import uvicorn
    app = create_sse_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)

