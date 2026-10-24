# Discord Compromise Cleanup

If your Discord account got hacked and the bot sent spam DMs, created phishing
events in your servers, forced you to leave group chats, blocked people, or
toggled the "Ignore messages" state on your friends — this tool reverses what
it did, inside a time window you specify.

Single-file Python script. GUI by default, CLI mode for scripters. No pip
install. Works on Windows, macOS, Linux.

---

## ⚠ Terms of service warning

**Using a user token to automate Discord actions violates
[Discord's Terms of Service](https://discord.com/terms) (section 3,
"Automated usage of Discord"). Discord may invalidate the token or ban
the account.**

The script paces its API calls slowly (default 2.5 s between calls) to
minimize but not eliminate the risk. Only you can decide whether the
risk is worth it for compromise recovery. If your attack is small
(a handful of DMs), manual deletion in the Discord app is strictly
safer.

---

## Before you run anything

Do these first. If you skip them, the attacker's session is still live
and anything you clean up gets re-spammed.

1. **Change your Discord password.** User Settings → My Account → Edit.
   This invalidates every existing token, including the attacker's.
2. **Enable two-factor authentication.** Same screen. Any authenticator
   app works. Save the backup codes somewhere offline.
3. **Revoke authorized apps.** User Settings → Authorized Apps. Remove
   anything you don't recognize. **These apps keep working after a
   password change** — a malicious app is how the attacker gets back in.
4. **Log out all devices.** User Settings → Devices → "Log Out All
   Known Devices". Requires your (new) password. The script can't do
   this for you.

Once those four are done, grab a fresh token and run the cleanup.

---

## How to get your Discord user token

**You need the Discord web app at [discord.com/app](https://discord.com/app).
The desktop client disables DevTools and this won't work.**

### Option A — DevTools (one-time, no install)

1. Log into `discord.com/app` with your **new** password.
2. Press `Ctrl+Shift+I` (`Cmd+Opt+I` on macOS) to open DevTools.
3. Click the **Network** tab, type `/api` in the filter.
4. In Discord itself, click any server or channel so some API traffic fires.
5. Click any `discord.com/api/v9/…` request in the Network panel.
6. Scroll the right panel to **Request Headers** → find `Authorization:`
   and copy its value.

Discord's Console tab shows a red "STOP!" warning telling you not to
paste anything a stranger gives you. That warning is for people being
scammed. You're copying your own token out, which is fine.

### Option B — Chrome extension (easier)

The [Discord Token Checker extension](https://chromewebstore.google.com/detail/discord-token-checker/lgdoombkkahcmffklnieoakenhakmjmk)
reads your currently-logged-in token out of the browser and lets you
copy it. Install, open Discord in Chrome, click the extension icon,
copy the token. Then uninstall the extension when you're done so
nothing else can read your token.

Either way, **never paste your token into a chat, screenshot, or
anywhere you don't control.** The token is a long-lived credential.

---

## Running the tool

### Windows

1. Install Python 3.9 or later from [python.org/downloads](https://www.python.org/downloads/).
   During install, **check "Add python.exe to PATH"**.
2. Download `discord-compromise-cleanup.py` from this repo
   (click the file → "Download raw file").
3. Double-click the downloaded file. The GUI opens.

### macOS

1. Install Python 3.9 or later from [python.org/downloads](https://www.python.org/downloads/).
2. Right-click `discord-compromise-cleanup.py` → Open With → Python
   Launcher. GUI opens.

### Linux

1. Make sure Python 3.9+ and Tkinter are present. On Ubuntu/Debian:
   `sudo apt install python3 python3-tk`. Most desktop distros have
   these preinstalled.
2. `python3 discord-compromise-cleanup.py` (or make it executable and
   double-click from the file manager).

### Headless / scripters

The script runs in CLI mode when invoked with `--cli`:

```bash
python3 discord-compromise-cleanup.py --cli \
    --token-file ~/.discord-token \
    --window-start 2026-10-23T03:30:00Z \
    --window-end   2026-10-23T18:00:00Z \
    --go
```

Pass `--help` for all flags.

---

## What the GUI does

1. **Big red banner at top** reminds you to change your password + 2FA
   + revoke apps + log out devices first.
2. **Token field** — paste the token here (masked), or load from a
   local file.
3. **Window** — Start and End in UTC. Defaults to the last 24 hours.
   Pick the window to cover from when the attack started to when you
   secured the account.
4. **Phase checkboxes** — pick which cleanups to run:
   - **DMs** — scan every DM channel (friends and non-friends), delete
     your messages posted in the window that match a compromise shape.
   - **Group DMs** — same, inside group chats.
   - **Group DM departures (report only)** — lists group chats you
     left during the window and who removed you. Nothing to delete here
     because Discord doesn't let you undo a leave through the API; a
     current member has to re-add you.
   - **Server scheduled events** — delete events your account created
     that carry a phishing lure (`discord.gg/` invite in the location,
     or `FREE NITRO` / `FREE NSFW` style name).
   - **Server messages** — delete your messages in each server search
     API returns that match the compromise shape.
   - **Unblock / unignore / cancel requests** — clear everything the
     bot might have set on your relationships: unblock, cancel outgoing
     friend requests, unignore friends, and blanket-clear the "ignore
     messages" state on every DM recipient (friends and non-friends).
5. **API pacing** — seconds between calls. Default 2.5 is slow enough
   to usually stay under Discord's selfbot detector. Lower is faster
   but riskier.
6. **Scan (dry run)** — enumerate everything and list what would be
   deleted. Deletes nothing.
7. **Delete (execute)** — asks for confirmation, then actually runs the
   deletions. Writes a `discord-cleanup-audit.json` audit log next to
   the script with every action it took.

---

## What the tool identifies as "compromise"

### Messages

A message you authored, inside the window, is treated as compromise if:

- it carries one or more **attachments** and the text is **either empty
  or just a bare `<@id>` mention** (classic attachment-and-bait pattern), **OR**
- the text contains a known **phishing URL or lure phrase**:
  `discord.gift/`, `dsc.gg/`, `discordapp.gift/`, `nitro gift`, `free nitro`,
  `free robux`, `gifted nitro`, `steamcommunity.com/`, `airdrop`,
  `@everyone`, `@here`.

Normal messages (a screenshot with descriptive text, a Spotify link,
your own apology to a friend) do not match either rule and are left
alone.

Standard server invite URLs (`discord.gg/*`) are **not** on the
phishing list, because people share real server invites all the time
and matching them would delete legitimate messages. If the attacker
sent a server-invite URL, the script may miss it — delete manually.

### Scheduled events

An event your account created is treated as compromise if **both**:

- `creator_id` is your user id, **AND**
- the location is a Discord invite URL (`discord.gg/`, `dsc.gg/`,
  `discord.gift/`), **OR** the name or description matches a bait
  phrase (`FREE NITRO`, `FREE NSFW`, nitro giveaway, airdrop, etc.).

Your own real events (D&D sessions, movie nights) don't match the
second rule and are left alone.

### Ignore / block state

Discord has two separate per-user silence states:

- **Blocked** — `relationship.type == 2`. Blocks all contact. The
  script unblocks everyone.
- **Ignored** — a per-user flag that hides their messages from your
  view without blocking. The flag appears on friend relationships
  (`relationship.user_ignored`) **and** on non-friend DMs (not surfaced
  on any REST endpoint I've found). The script clears both by iterating
  every DM recipient and calling the unignore endpoint; Discord returns
  204 on no-ops, so this is safe.

### Outgoing friend requests

The script cancels every pending outgoing friend request (`type == 4`).
If the attacker added accomplice accounts as friends to maintain
access, this cuts that off.

---

## What the tool does NOT do

- **Does not log out your other sessions.** The REST endpoint for that
  requires your password. Do it manually in User Settings → Devices.
- **Does not undo group DM leaves.** Discord's API has no "rejoin"
  action. A current member has to re-add you.
- **Does not delete messages from channels you don't have VIEW on.**
  If the attacker got you kicked from a server before the event
  deletion ran, those messages are now out of reach.
- **Does not touch servers you no longer belong to.** Same reason.
- **Does not delete your own apology messages.** You can delete those
  manually if you want a clean slate.

---

## Risk mitigations the script uses

- **Dry run by default.** Click "Scan" first, review what would be
  deleted, click "Delete" only when the list looks right.
- **Slow API pacing** (2.5 s/call default) to stay under Discord's
  automation detector.
- **Honors Discord's `Retry-After` on 429s.**
- **Aborts cleanly on 401** so you catch a token-kill fast instead of
  looping into a ban.
- **Writes a JSON audit log** (`discord-cleanup-audit.json`) of every
  deletion with timestamps, so you can trace what was done.

---

## Known limits

- The script enumerates DM channels via `/users/@me/channels`, which
  only lists currently-visible DMs. If the attacker DM'd someone whose
  channel got auto-dismissed before you ran this, their DM is
  invisible until you re-open the DM (which POST-opens the channel on
  Discord's side). The script already POST-opens every friend's DM to
  cover that case.
- The guild message search endpoint returns 429 or 403 for some
  servers (large guilds, lack of search permission). The script skips
  those gracefully and reports the count.
- Discord sometimes caches sidebar state on the mobile client. If a
  DM still shows "Ignored" after running the script, pull-to-refresh
  the DM list or restart the app.

---

## License

MIT. Use at your own risk; see the ToS warning above.

---

## Contributing

PRs welcome, especially for:

- Additional compromise signatures as new attack patterns emerge
- A proper Windows `.exe` build (PyInstaller) so Python doesn't need
  to be installed first
- GitHub Actions release pipeline that produces prebuilt binaries for
  Windows, macOS, and Linux
