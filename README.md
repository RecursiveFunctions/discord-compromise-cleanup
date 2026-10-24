
# Discord Compromise Cleanup

You (or someone you know) got their discord account hacked. The bot sent spam, made phishing events, blocked
your friends, hid their messages. This will reverse what the bot did.

Works on windows/Linux/Mac. 

## ⚠ Terms of service warning

Using a user token to automate Discord actions violates [Discord's
ToS](https://discord.com/terms) (section 3). Your account can be banned.
The script paces slow (2.5 s/call) to minimize detection but can't
eliminate it. unlikely here but worth mentioning.

## Pre-flight

Do these before running. If you skip them, the attacker's session is
still live and anything you clean up gets re-spammed.

| step | Discord Desktop / Web | Discord Mobile (iOS / Android) |
|---|---|---|
| **1. Change your password** | User Settings → My Account → Edit → Password | Settings (gear ⚙ bottom-right) → My Account → Password |
| **2. Enable 2FA** | My Account → "Enable Two-Factor Auth" | My Account → "Enable Two-Factor Auth" |
| **3. Revoke Authorized Apps** — these keep working after a password change | User Settings → Authorized Apps | Settings → Authorized Apps (scroll down the settings list) |
| **4. Log out all devices** | User Settings → Devices → "Log Out All Known Devices" | Settings → Devices → "Log Out All Known Devices" |

Save your 2FA backup codes somewhere offline (notes app, paper). You
can't do step 4 from the cleanup tool; it needs your password.

## Get your Discord token

**You need [discord.com/app](https://discord.com/app) in a browser.**
The Discord desktop app disables DevTools and the mobile app has no
way to export tokens. All three options below work in a browser.

### Option A — Chrome extension (desktop, easiest)

Install [Discord Token
Checker](https://chromewebstore.google.com/detail/discord-token-checker/lgdoombkkahcmffklnieoakenhakmjmk),
log into Discord in Chrome, click the extension icon, copy the token.
Uninstall the extension when done.

### Option B — DevTools (desktop, no install)

1. Log into `discord.com/app` with your new password.
2. `Ctrl+Shift+I` (`Cmd+Opt+I` on macOS) → **Network** tab → filter `/api`.
3. Click any channel in Discord. Click any `/api/v9/…` request in Network.
4. Request Headers → copy the `Authorization:` value.

### Option C — Phone only (bookmarklet)

If you only have a phone, you can still do this through the mobile browser:

1. Open your browser (**Safari on iOS**, **Chrome on Android**).
2. Go to [discord.com/app](https://discord.com/app).
   - On iOS: tap the `aA` button in the address bar → "Request
     Desktop Website".
   - On Android: tap the ⋮ menu → check "Desktop site".
3. Log in with your new password.
4. **Save this as a bookmark** (any URL, e.g. `https://example.com`):

   <details>
   <summary>Click to show the bookmarklet JavaScript (long)</summary>

   ```
   javascript:(function(){try{var i=document.createElement('iframe');document.body.appendChild(i);var r=i.contentWindow.webpackChunkdiscord_app.push([[Symbol()],{},function(x){return x;}]);var t=null;for(var k in r.c){var m=r.c[k];if(m&&m.exports){var e=m.exports.default||m.exports;if(e&&typeof e.getToken==='function'){t=e.getToken();break}}}document.body.removeChild(i);if(!t){alert('Token not found. Discord may have updated. Borrow a desktop/laptop.');return}navigator.clipboard.writeText(t).then(function(){alert('Token copied to clipboard. Paste it into the cleanup tool.')},function(){prompt('Clipboard denied. Copy the token below:',t)})}catch(e){alert('Error: '+e.message)}})();
   ```
   </details>

   Edit the saved bookmark → replace its URL with the whole
   `javascript:…` block above. Name it something like **"Get Discord
   token"**.
5. In the **same browser tab** where you're logged into Discord,
   tap the address bar, start typing the bookmark name, tap it.
   An alert says "Token copied to clipboard". If it doesn't,
   Discord changed something — fall back to a desktop/laptop.

Then open the cleanup tool and paste.

### Common to all three options

- Ignore Discord's red "STOP!" warning in DevTools — that message is
  for people being scammed, you're copying your own token.
- **Never paste your token into a chat, screenshot, or anywhere you
  don't control.** The token is a long-lived credential; anyone with
  it can read everything your account can see.

## How to run

**Easiest — download the prebuilt binary** from the
[latest release](https://github.com/RecursiveFunctions/discord-compromise-cleanup/releases/latest).

Pick the one matching your OS, then:

- **Windows** → `discord-compromise-cleanup-windows.exe`, double-click.
  Windows will show **"Windows protected your PC"** because the binary
  isn't signed by a $300/yr Microsoft code-signing cert. Click
  **"More info"** at the top of that dialog, then **"Run anyway"** at
  the bottom. The file is open source — you can read every line in
  this repo.
- **macOS** → `discord-compromise-cleanup-macos`. The first time:
  **right-click the file → Open** (not double-click), then click
  **"Open"** on the "unverified developer" dialog. Same reason as
  Windows — not code-signed. Second time onward, double-click works.
- **Linux** → `discord-compromise-cleanup-linux`. In a terminal:
  `chmod +x discord-compromise-cleanup-linux && ./discord-compromise-cleanup-linux`.
  Or set executable in your file manager (right-click → Properties →
  Permissions → "Allow executing") and double-click.

No Python install needed. Downloads are ~10 MB (self-contained).

<details>
<summary><b>Run from source</b> (requires Python 3.9+, use this if the
binary doesn't work for your OS or you want to read / modify the code)</summary>

**Step 1 — get the code.** Either clone the repo (needs Git):

```bash
git clone https://github.com/RecursiveFunctions/discord-compromise-cleanup.git
cd discord-compromise-cleanup
```

Or, if you don't have Git, [download the ZIP](https://github.com/RecursiveFunctions/discord-compromise-cleanup/archive/refs/heads/master.zip)
and unzip it. All you actually need from the repo is the single file
`discord-compromise-cleanup.py` — you can also just save that file
directly from
[its raw view](https://raw.githubusercontent.com/RecursiveFunctions/discord-compromise-cleanup/master/discord-compromise-cleanup.py)
(right-click → Save As).

**Step 2 — make sure Python 3.9+ is installed.**

- **Windows / macOS:** [python.org/downloads](https://www.python.org/downloads/).
  On Windows, check **"Add python.exe to PATH"** during install.
- **Linux:** `sudo apt install python3 python3-tk`
  (or your distro's equivalent).

**Step 3 — launch.**

- Double-click `discord-compromise-cleanup.py` (Windows / macOS /
  Linux file managers all support this).
- Or from a terminal: `python3 discord-compromise-cleanup.py`.

**CLI mode (scripters):**

```bash
python3 discord-compromise-cleanup.py --cli --token-file ~/.discord-token --go
```

Pass `--help` for all flags.
</details>

## What a compromise looks like

### Scheduled events

![example compromise event](docs/examples/example-scheduled-event.jpg)

Pattern: your account creates an event with a lure name (`FREE NSFW`,
`FREE NITRO`, airdrop) linking to a `discord.gg/` invite the attacker
controls. Server members get notified, think it's from you, (and now they think you're a gooner)

### DM spam

Pattern: a short message with 4 image attachments and content that's
either empty or just a bare `<@mention>` of the recipient. The
attachments are the lure (fake Nitro gift, fake crypto airdrop, QR
code to a phishing site). The bot DMs every friend plus people in
your contacts list

Variants also seen in the wild: text messages with `discord.gift/`,
`dsc.gg/`, nitro gift URLs, `free robux`, `@everyone`, `@here`.

### Relationship-state abuse

- Blocks your friends so you can't see them
- Toggles the "Ignore messages" state on your friends and DMs
- Sends outgoing friend requests to accomplice accounts
- Removes you from group chats (not undoable)

## What the GUI does

![](docs/examples/gui-screenshot.png)

1. Paste token (masked) or load from file.
2. Set the compromise window in UTC. **Default = last 24 h is fine for
   most people** — don't touch it unless you need to.
   If you need custom bounds and don't know what UTC is, open
   [timeanddate.com/worldclock/converter.html](https://www.timeanddate.com/worldclock/converter.html),
   convert the start and end moments from your local time to UTC, and
   paste those into the fields. Example: 11:30 PM Eastern on Oct 22 =
   `2026-10-23 03:30` in UTC (Eastern is 4 hours behind UTC).
3. Pick phases: DMs, group DMs, group departures (report-only), server
   events, server messages, relationships.
4. **Scan (dry run)** — lists what would be deleted, deletes nothing.
5. **Delete (execute)** — confirms, then runs. Writes
   `discord-cleanup-audit.json` next to the script.
6. **Stop** — enabled while a scan or delete is running. Click any time
   to cancel: the engine finishes the current API call (max 1-2 s),
   writes a partial audit log if it was deleting, and the GUI returns
   to idle. Safe to use mid-run; nothing is left in a half-done state.

## What it looks for

**Messages — delete if either:**
- 1+ attachment AND content is empty or just `<@id>`, OR
- content matches `discord.gift/ | dsc.gg/ | discordapp.gift/ | nitro.gift
  | free (nitro|robux) | gifted nitro | steamcommunity.com/ | airdrop
  | @everyone | @here`

Normal `discord.gg/` server invites are **not** flagged (people share
legit invites). If the attacker shared a server invite, delete manually.

**Events — delete if all:**
- `creator_id == you`, AND
- location is a `discord.gg/` / `dsc.gg/` / `discord.gift/` URL, OR
  name/description matches the lure regex (`FREE NSFW/NITRO/ROBUX`,
  nitro giveaway, airdrop).

Your real events (D&D night, movie watch) stay.

**Relationships:**
- All blocks removed
- All outgoing friend requests cancelled
- All friend-ignores cleared
- `DELETE /users/@me/relationships/{uid}/ignore` on every DM recipient
  (covers non-friend DM-level ignore, which no REST endpoint surfaces)

## Troubleshooting

**"I still see 'Ignored message' badges on my DMs after running it."**
Discord's mobile and desktop apps cache the ignore state locally and
don't refresh it until the WebSocket reconnects. **Fully quit and reopen
the app** (not just background it — kill it from the recent apps list on
mobile, or File → Quit on desktop). The badges clear on the fresh
connection.

**"The GUI opens but nothing happens when I click Scan."** The button
is disabled while fields are invalid. Check that the token field has a
value, the window has start < end in `YYYY-MM-DD HH:MM` format, and at
least one phase checkbox is ticked.

**"Discord revoked my token mid-run."** Discord's anti-automation
system saw too many API calls too fast. Grab a fresh token (your
account is fine, just that session is invalid), raise the pacing in the
GUI from 2.5 → 4.0 seconds per call, and re-run. The partial audit log
tells you what was already done so you don't repeat work.

**"The mobile bookmarklet alert says 'Token not found'."** Discord
updates their internal module layout a few times a year, which can
break the bookmarklet. Workaround: borrow a laptop or desktop for 10
minutes and use the DevTools or Chrome extension method.

**"PyInstaller binary won't launch on an older OS."** The binaries are
built on current Windows 10, macOS 14, and Ubuntu 22.04. If your OS is
older, use the "Run from source" path with your system's Python.

## What it does NOT do

- **Log out other sessions.** That endpoint needs your password.
- **Undo group DM leaves.** No API for it; a member has to re-add you.
- **Touch servers you got kicked from.** Can't see them anymore.
- **Delete `discord.gg/` server invites.** Too many false positives.
- **Delete your own apology messages.** Those are yours to keep.

## Risk mitigations the script uses

- Dry-run default (click Scan before Delete)
- 2.5 s/call default pacing (adjustable)
- Honors Discord's `Retry-After` on 429s
- Aborts on 401 so a token-kill doesn't loop into a ban
- JSON audit log of every deletion

## License

MIT. Use at your own risk; see the ToS warning.
