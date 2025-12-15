#!/usr/bin/env python3
"""
Test script for the Financial MCP server running in SSE mode.

Supports Bearer token authentication via:
  - --token <token> argument
  - MCP_AUTH_TOKEN environment variable
"""
import asyncio
import os
from mcp import ClientSession
from mcp.client.sse import sse_client
import dotenv
dotenv.load_dotenv()

SERVER_URL = "http://localhost:8000/sse"

# Get auth token from environment or command line
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")


def get_headers():
    """Get HTTP headers including auth if configured."""
    if AUTH_TOKEN:
        return {"Authorization": f"Bearer {AUTH_TOKEN}"}
    return {}


async def test_list_tools():
    """List all available tools from the server."""
    print(f"Connecting to {SERVER_URL}...")
    if AUTH_TOKEN:
        print("Using authentication token")
    
    async with sse_client(SERVER_URL, headers=get_headers()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("\n" + "=" * 60)
            print("Available Tools")
            print("=" * 60)
            
            tools_result = await session.list_tools()
            
            for tool in tools_result.tools:
                print(f"\n📌 {tool.name}")
                print(f"   {tool.description}")
                if tool.inputSchema and tool.inputSchema.get("properties"):
                    print("   Arguments:")
                    for prop_name, prop_details in tool.inputSchema["properties"].items():
                        default = prop_details.get("default", "")
                        default_str = f" (default: {default})" if default else ""
                        print(f"     - {prop_name}: {prop_details.get('type', 'any')}{default_str}")
            
            print(f"\n✅ Total: {len(tools_result.tools)} tools available")


async def test_call_tool(tool_name: str, arguments: dict = None):
    """Call a specific tool and display the result."""
    print(f"\nConnecting to {SERVER_URL}...")
    if AUTH_TOKEN:
        print("Using authentication token")
    
    async with sse_client(SERVER_URL, headers=get_headers()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print(f"\n🔧 Calling: {tool_name}")
            if arguments:
                print(f"   Arguments: {arguments}")
            
            result = await session.call_tool(tool_name, arguments=arguments or {})
            
            if result.content:
                text = result.content[0].text
                # Truncate if very long
                if len(text) > 2000:
                    print(f"\n{text[:2000]}...\n\n[Truncated - {len(text)} total chars]")
                else:
                    print(f"\n{text}")
            else:
                print("No content returned.")


async def run_full_test():
    """Run a comprehensive test of all tools."""
    print("=" * 60)
    print("Financial MCP Server - Full Test")
    print("=" * 60)
    if AUTH_TOKEN:
        print("Using authentication token")
    
    async with sse_client(SERVER_URL, headers=get_headers()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List tools first
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"\n✅ Connected! Found {len(tool_names)} tools: {', '.join(tool_names)}")
            
            # Test Monobank tools
            if "monobank_get_client_info" in tool_names:
                print("\n" + "-" * 40)
                print("Testing: monobank_get_client_info")
                print("-" * 40)
                try:
                    result = await session.call_tool("monobank_get_client_info")
                    if result.content:
                        print(result.content[0].text[:500])
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            if "monobank_get_portfolio" in tool_names:
                print("\n" + "-" * 40)
                print("Testing: monobank_get_portfolio")
                print("-" * 40)
                try:
                    result = await session.call_tool("monobank_get_portfolio")
                    if result.content:
                        print(result.content[0].text[:500])
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            # Test Wise tools
            if "wise_get_profiles" in tool_names:
                print("\n" + "-" * 40)
                print("Testing: wise_get_profiles")
                print("-" * 40)
                try:
                    result = await session.call_tool("wise_get_profiles")
                    if result.content:
                        print(result.content[0].text[:500])
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            if "wise_get_balances" in tool_names:
                print("\n" + "-" * 40)
                print("Testing: wise_get_balances")
                print("-" * 40)
                try:
                    result = await session.call_tool("wise_get_balances")
                    if result.content:
                        print(result.content[0].text[:500])
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            # Test Report tool
            if "generate_report" in tool_names:
                print("\n" + "-" * 40)
                print("Testing: generate_report (days=7)")
                print("-" * 40)
                try:
                    result = await session.call_tool("generate_report", arguments={"days": 7})
                    if result.content:
                        text = result.content[0].text
                        print(text[:1000] + "..." if len(text) > 1000 else text)
                except Exception as e:
                    print(f"❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)


def print_usage():
    print("Usage:")
    print("  python test_mcp_server.py [--token TOKEN] list              - List all tools")
    print("  python test_mcp_server.py [--token TOKEN] call <tool> [args] - Call a specific tool")
    print("  python test_mcp_server.py [--token TOKEN] full              - Run full test suite")
    print("")
    print("Authentication:")
    print("  --token TOKEN        Pass auth token via command line")
    print("  MCP_AUTH_TOKEN env   Or set this environment variable")
    print("")
    print("Examples:")
    print("  python test_mcp_server.py list")
    print("  python test_mcp_server.py --token mysecret list")
    print("  MCP_AUTH_TOKEN=mysecret python test_mcp_server.py list")
    print("  python test_mcp_server.py call monobank_get_portfolio")
    print("  python test_mcp_server.py call generate_report days=7")


if __name__ == "__main__":
    import sys
    
    # Parse --token argument
    args = sys.argv[1:]
    if "--token" in args:
        idx = args.index("--token")
        if idx + 1 < len(args):
            AUTH_TOKEN = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("Error: --token requires a value")
            sys.exit(1)
    
    if len(args) > 0:
        cmd = args[0]
        if cmd == "list":
            asyncio.run(test_list_tools())
        elif cmd == "call" and len(args) > 1:
            tool_name = args[1]
            # Simple arg parsing: key=value pairs
            tool_args = {}
            for arg in args[2:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    # Try to parse as int
                    try:
                        v = int(v)
                    except ValueError:
                        pass
                    tool_args[k] = v
            asyncio.run(test_call_tool(tool_name, tool_args))
        elif cmd == "full":
            asyncio.run(run_full_test())
        elif cmd in ["--help", "-h", "help"]:
            print_usage()
        else:
            print_usage()
    else:
        # Default: list tools
        asyncio.run(test_list_tools())

