# Token connector

A token connector is the host's Supabase connector set up with a personal
access token instead of the connector's sign-in. A small helper script reads
the token from the secret store of the computer and gives it to the connector.
Use it in these cases:

- You use several Claude Code profiles. Claude Code stores the connector's
  sign-in for each configuration folder, so each profile needs its own
  sign-in.
- You use Codex without a connected Supabase app.

One token and one helper script serve Claude Code and Codex, and every
profile of one computer. The steps are for macOS and Linux. Tested versions:
Claude Code 2.1.322 and Codex 0.167.0.

Type the token only at the prompts below. Do not paste it into a conversation
with an agent, into a command line, or into a file in a repository. An agent
that follows these steps leaves each prompt to you. The plugin ships no copy
of the helper script and never reads the token.

## 1. Create the token

1. Open `https://supabase.com/dashboard/account/tokens`.
2. Create a token that can access only your GTD project.
3. Give the token these permissions, from the
   [Supabase list of permissions for MCP tools](https://supabase.com/docs/guides/platform/personal-access-tokens#mcp-tools):
   - Database (Read), for `execute_sql`.
   - Projects (Read), for `list_projects`.
   - For `gtd-setup` on a new database, also Migrations (Read-write), for
     `apply_migration`.
4. Copy the token. Supabase shows it one time.

## 2. Store the token

On macOS, store the token in the Keychain. The command asks for the token two
times, and it replaces a stored token:

```bash
security add-generic-password -U -a "$USER" -s cc-toolkit-supabase-pat -w
```

On Linux, store the token in an owner-only file. The command asks for the
token and does not show it:

```bash
bash -c 'umask 077; mkdir -p "$HOME/.config/cc-toolkit"; IFS= read -rsp "Supabase token: " t; echo; printf "%s\n" "$t" > "$HOME/.config/cc-toolkit/supabase-pat"; chmod 600 "$HOME/.config/cc-toolkit/supabase-pat"'
```

To copy the token from a Mac to a Linux computer, send it through `ssh`. The
token does not appear on the screen or on a command line:

```bash
security find-generic-password -s cc-toolkit-supabase-pat -w |
  ssh <host> 'umask 077; mkdir -p ~/.config/cc-toolkit; cat > ~/.config/cc-toolkit/supabase-pat; chmod 600 ~/.config/cc-toolkit/supabase-pat'
```

From a Linux computer, replace the first line with
`cat ~/.config/cc-toolkit/supabase-pat |`. To put the token on a Mac, use the
Keychain command above on that Mac.

## 3. Save the helper script

1. Save this text as `~/.config/cc-toolkit/supabase-mcp-headers.sh`:

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

2. Make the script executable:

   ```bash
   chmod 700 ~/.config/cc-toolkit/supabase-mcp-headers.sh
   ```

3. Check the script. The command prints `ok` and does not show the token:

   ```bash
   ~/.config/cc-toolkit/supabase-mcp-headers.sh > /dev/null && echo ok
   ```

## 4. Connect Claude Code

Do these steps in each Claude Code profile. For a profile other than the
default, put `CLAUDE_CONFIG_DIR=<profile folder>` before each `claude`
command.

1. If `claude mcp list` shows a `supabase` connector, remove it with
   `claude mcp remove supabase`.
2. Add the connector:

   ```bash
   helper="$HOME/.config/cc-toolkit/supabase-mcp-headers.sh"
   claude mcp add-json --scope user supabase "{\"type\":\"http\",\"url\":\"https://mcp.supabase.com/mcp\",\"headersHelper\":\"$helper\"}"
   ```

3. Run `claude mcp list`. The `supabase` line shows `✔ Connected`.

This connector has the same URL as the connector of the Supabase plugin, so
it replaces the plugin's connector. You do not need the plugin's sign-in.

## 5. Connect Codex

`codex mcp add` has no option for a helper script, so edit the Codex
configuration file: `~/.codex/config.toml`, or `config.toml` in
`$CODEX_HOME`.

1. Get the absolute path of the helper script:

   ```bash
   echo "$HOME/.config/cc-toolkit/supabase-mcp-headers.sh"
   ```

2. If the file has a `[mcp_servers.supabase]` table, remove that table.
3. Add this table. Replace `<helper>` with the path from item 1:

   ```toml
   [mcp_servers.supabase]
   url = "https://mcp.supabase.com/mcp"
   http_headers_helper = "<helper>"
   ```

4. If you signed in with `codex mcp login supabase`, run
   `codex mcp logout supabase`. Codex uses a stored sign-in for this
   connector before the helper.

If you use more than one `CODEX_HOME` folder, do these steps for the
`config.toml` of each folder.

## 6. Check and maintain

1. Start a new session, and run `gtd-setup`. Its step 1 lists your projects
   through the connector.
2. Do not add `project_ref` or `read_only=true` to the connector URL. A
   `project_ref` removes `project_id` from the SQL tool, so the GTD queries
   fail with "Unrecognized key". `read_only=true` stops every GTD save.
3. To change the token, store the new token as in section 2. Then start new
   sessions.
4. To stop access, revoke the token on the Supabase token page.
