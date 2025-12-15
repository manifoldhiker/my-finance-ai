# Financial Agent

## MCP Server

Start the unified MCP server:
```bash
docker compose up -d
```

The server runs at `http://127.0.0.1:8000/sse` with optional Bearer auth (set `MCP_AUTH_TOKEN` env var).

### Connect to Claude Desktop

1. Open Claude Desktop → **Settings** → **Developer** → **Edit Config**
2. Add to `claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "my-finance-ai": {
         "type": "http",
         "uri": "http://127.0.0.1:8000/sse",
         "headers": {
           "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
         }
       }
     }
   }
   ```
   *(Omit `headers` if not using auth)*
3. Restart Claude Desktop completely (quit from menu bar, reopen)
4. Look for the hammer icon in chat to verify tools are available
