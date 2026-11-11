# Token connector

A token connector is the host's Supabase connector set up with a personal
access token instead of the connector's sign-in. A small helper script reads
the token from the secret store of the computer and gives it to the connector.
Use it when:

- you use several Claude Code profiles: the connector's sign-in is stored
  for each configuration folder, so each profile needs its own sign-in;
- you use Codex without a connected Supabase app.

One token and one helper script serve Claude Code and Codex, and every
profile of one computer. The steps are for macOS and Linux. They were tested
with Claude Code 2.1.322 and Codex 0.167.0.

Type the token only at the prompts below. Do not paste it into a conversation
with an agent, into a command line, or into a file in a repository. An agent
that follows these steps leaves each prompt to you. The plugin ships no copy
of the helper script and never reads the token.

## 1. Create the token

1. Open `https://supabase.com/dashboard/account/tokens`.
2. Create a token that can access only your GTD project.
3. Give it the permissions that the page lists for the MCP tools
   `execute_sql` and `list_projects`. For `gtd-setup` on a new database,
   also give the permission for `apply_migration`.
4. Copy the token. Supabase shows it one time.

## 2. Store the token

On macOS, store it in the Keychain. The command asks for the token two
times. Add `-U` to replace a stored token:

```bash
security add-generic-password -a "$USER" -s cc-toolkit-supabase-pat -w
```

On Linux, store it in an owner-only file. The command asks for the token and
does not show it:

```bash
bash -c 'umask 077; mkdir -p "$HOME/.config/cc-toolkit"; IFS= read -rsp "Supabase token: " t; echo; printf "%s\n" "$t" > "$HOME/.config/cc-toolkit/supabase-pat"'
```

To copy the token from a Mac to a Linux computer, send it through `ssh`. It
does not appear on the screen or on a command line:

```bash
security find-generic-password -s cc-toolkit-supabase-pat -w |
  ssh <host> 'umask 077; mkdir -p ~/.config/cc-toolkit; cat > ~/.config/cc-toolkit/supabase-pat'
```

## 3. Save the helper script

Save this text as `~/.config/cc-toolkit/supabase-mcp-headers.sh`. Then run
`chmod 700 ~/.config/cc-toolkit/supabase-mcp-headers.sh`.

```sh
#!/bin/sh
# Print the Supabase connector header for Claude Code (headersHelper)
# and Codex (http_headers_helper). The token stays in the secret store.
PATH="$PATH:/usr/bin:/bin"
if [ "$(uname)" = Darwin ]; then
  token=$(security find-generic-password -s cc-toolkit-supabase-pat -w 2>/dev/null)
else
  token=$(tr -d '[:space:]' 2>/dev/null < "$HOME/.config/cc-toolkit/supabase-pat")
fi
[ -n "$token" ] || { echo "Supabase token not found; see gtd-token-connector.md" >&2; exit 1; }
printf '{"Authorization":"Bearer %s"}\n' "$token"
```

Run the script one time to check it. It prints one line that starts with
`{"Authorization":"Bearer`. Do not share that line.

## 4. Connect Claude Code

Add a user-scope connector in each profile. For the default profile:

```bash
helper="$HOME/.config/cc-toolkit/supabase-mcp-headers.sh"
claude mcp add-json --scope user supabase "{\"type\":\"http\",\"url\":\"https://mcp.supabase.com/mcp\",\"headersHelper\":\"$helper\"}"
```

For another profile, put `CLAUDE_CONFIG_DIR=<profile folder>` before
`claude`. Then run `claude mcp list` in each profile. The `supabase` line
shows `✔ Connected`.

This entry has the same URL as the server of the Supabase plugin, so it
replaces that server. You do not need the plugin's sign-in.

## 5. Connect Codex

`codex mcp add` has no option for a helper script, so edit the Codex
configuration file: `~/.codex/config.toml`, or `config.toml` in
`$CODEX_HOME`. Replace `<helper>` with the absolute path that
`echo "$HOME/.config/cc-toolkit/supabase-mcp-headers.sh"` prints. If the file
has a `[mcp_servers.supabase]` table, replace that table.

```toml
[mcp_servers.supabase]
url = "https://mcp.supabase.com/mcp"
http_headers_helper = "<helper>"
```

A stored Codex sign-in for this server is used before the helper. If you
signed in with `codex mcp login supabase`, run `codex mcp logout supabase`.
Codex profiles that link to one `config.toml` need this step one time.

## 6. Check and maintain

1. Start a new session, and run `gtd-setup`. Its read check proves the
   connector.
2. Do not add `project_ref` or `read_only=true` to the connector URL. A
   `project_ref` removes `project_id` from the SQL tool, so the GTD queries
   fail with "Unrecognized key". `read_only=true` stops every GTD save.
3. To change the token, store the new token as in step 2, then start new
   sessions. To stop access, revoke the token on the Supabase token page.
