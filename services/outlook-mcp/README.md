# Outlook Mail MCP (read-only)

Minimal, controlled MCP server for delegated Microsoft Graph mail access.

## Tools (read-only)

| Tool | Purpose |
|------|---------|
| `outlook_search_messages` | Search mailbox with safe summaries |
| `outlook_get_message` | Read one message by ID |
| `outlook_list_folders` | List mailbox folders |
| `outlook_get_recent_messages` | Recent Inbox/folder messages |
| `outlook_get_attachment_text` | Safe text extraction (.txt, .md, .csv only) |

No send, delete, move, archive, or mark-as-read tools are exposed.

## Environment variables

```env
MONGO_URI=
MICROSOFT_CLIENT_ID=
MICROSOFT_TENANT_ID=common
MICROSOFT_REDIRECT_URI=
MICROSOFT_SCOPES=User.Read Mail.Read offline_access
MICROSOFT_TOKEN_ENCRYPTION_KEY=
INTERNAL_SERVICE_TOKEN=
OUTLOOK_MCP_LOG_LEVEL=INFO
```

OAuth connect/disconnect is handled by the API (`/integrations/outlook/*`). Tokens are stored encrypted in MongoDB collection `outlook_oauth_tokens`.

## Connect a Microsoft account

1. Set `MICROSOFT_CLIENT_ID` and `MICROSOFT_TOKEN_ENCRYPTION_KEY` in `.env`.
2. Register redirect URI: `${WEB_APP_URL}/api/integrations/outlook/callback`.
3. Grant delegated permissions: `User.Read`, `Mail.Read`, `offline_access`.
4. Sign in to UniPilot, then open **Integrations** in the sidebar (`/settings/integrations`) and click **Connect Outlook**.

## Run locally

```bash
cd services/outlook-mcp
pip install -r requirements-dev.txt
python -m app.main
```

## Run tests

```bash
cd services/outlook-mcp
pytest
```

## Agent MCP configuration (Cursor example)

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "unipilot-outlook": {
      "command": "python",
      "args": ["-m", "app.main"],
      "cwd": "services/outlook-mcp",
      "env": {
        "MONGO_URI": "mongodb://...",
        "MICROSOFT_CLIENT_ID": "...",
        "MICROSOFT_TOKEN_ENCRYPTION_KEY": "...",
        "INTERNAL_SERVICE_TOKEN": "..."
      }
    }
  }
}
```

Each tool call must include:

- `userId` — UniPilot user ObjectId (mailbox owner)
- `internalToken` — matches `INTERNAL_SERVICE_TOKEN`

## Security

- Delegated OAuth only (`User.Read`, `Mail.Read`, `offline_access`)
- Tokens encrypted at rest (Fernet)
- Audit logs redact tokens and message bodies
- All email text returned with `trusted: false` and prompt-injection warning
- `maxResults` capped at 25
- Attachment text limited to safe types and 256 KB
