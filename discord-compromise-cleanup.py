#!/usr/bin/env python3
"""
Discord Compromise Cleanup — GUI + CLI, cross-platform, zero-dep.

Run it:
  Windows:  double-click discord-compromise-cleanup.py  (or: py discord-compromise-cleanup.py)
  Linux:    python3 discord-compromise-cleanup.py
  macOS:    python3 discord-compromise-cleanup.py

No pip install needed. Only requirement: Python 3.8 or later with Tkinter
(bundled by default on Windows & macOS; on Linux: `sudo apt install python3-tk`).

For scripting / power users, use --cli with --token-file. Pass --help for flags.

                              ⚠️  USAGE DANGER  ⚠️
Using a user token to automate Discord actions is **selfbotting** and
violates Discord's Terms of Service. Discord may invalidate the token or
ban the account. Slow pacing minimizes but doesn't eliminate the risk.
Only you can decide whether the risk is worth it for compromise recovery.
"""

import argparse
import json
import os
import queue
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://discord.com/api/v9"
DISCORD_EPOCH = 1420070400000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) discord/1.0.9174 Chrome/128.0.0.0 "
      "Electron/32.2.6 Safari/537.36")

# ---------- compromise signatures ----------

MENTION_ONLY_WITH_ATTACHMENT = re.compile(r"^\s*<@!?\d+>\s*$")
PHISH_PATTERNS = re.compile(
    r"(?i)discord\.gift/|dsc\.gg/|discordapp\.gift/|nitro.?gift|"
    r"free.?(nitro|robux)|gifted?.{0,20}nitro|steamcommunity\.com/|"
    r"steamgift|airdrop|@everyone|@here"
)
EVENT_PHISH_LOCATION = re.compile(r"(?i)discord\.gg/|dsc\.gg/|discord\.gift/")
EVENT_PHISH_NAME = re.compile(
    r"(?i)free.?(nsfw|nitro|robux|porn|onlyfans|gift)|"
    r"nitro.?(gift|drop|airdrop)|airdrop|"
    r"[⬇📥]{1,3}.{0,30}(join|free|gift|nsfw)|"
    r"(join|get).{0,20}(our|free).{0,10}(server|discord|nitro)"
)


def is_compromise_message(my_id, msg, min_sf, max_sf) -> bool:
    try:
        mid = int(msg["id"])
    except (KeyError, ValueError):
        return False
    if not (min_sf <= mid <= max_sf):
        return False
    if msg["author"]["id"] != my_id:
        return False
    content = (msg.get("content") or "").strip()
    natt = len(msg.get("attachments", []))
    if natt >= 1 and (content == "" or MENTION_ONLY_WITH_ATTACHMENT.match(content)):
        return True
    if PHISH_PATTERNS.search(content):
        return True
    return False


def is_compromise_event(my_id, ev) -> bool:
    if ev.get("creator_id") != my_id:
        return False
    name = ev.get("name") or ""
    desc = ev.get("description") or ""
    location = (ev.get("entity_metadata") or {}).get("location") or ""
    if EVENT_PHISH_LOCATION.search(location):
        return True
    if EVENT_PHISH_NAME.search(name) or EVENT_PHISH_NAME.search(desc):
        return True
    return False


# ---------- API ----------

class Cleanup:
    """Core engine. One instance per run. Thread-safe-ish via a progress queue."""

    def __init__(self, token, min_sf, max_sf, pace=2.5, go=False, progress=None):
        self.token = token
        self.min_sf = min_sf
        self.max_sf = max_sf
        self.pace = pace
        self.go = go
        self.progress = progress or (lambda *a, **k: None)
        self.audit = []
        self.aborted = False

    def log(self, line):
        self.progress(("log", line))

    def phase(self, name, pct):
        self.progress(("phase", name, pct))

    def _sleep(self):
        time.sleep(self.pace + random.random())

    def api(self, method, path, data=None, retries=6):
        headers = {"Authorization": self.token, "User-Agent": UA,
                   "Content-Type": "application/json"}
        for attempt in range(retries):
            req = urllib.request.Request(API + path, method=method, headers=headers)
            if data is not None:
                req.data = json.dumps(data).encode()
            try:
                r = urllib.request.urlopen(req, timeout=20)
                return (r.status, None) if r.status == 204 else (r.status, json.loads(r.read()))
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    self.log("!!! Discord revoked the token mid-run. Stopping.")
                    self.aborted = True
                    raise SystemExit(2)
                if e.code == 429:
                    try:
                        wait = float(json.loads(e.read()).get("retry_after", 3))
                    except Exception:
                        wait = float(e.headers.get("Retry-After", "3"))
                    self.log(f"  (rate-limited, waiting {wait+1:.1f}s)")
                    time.sleep(wait + 1)
                    continue
                if e.code in (403, 404):
                    return e.code, None
                if e.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                return e.code, None
            except (TimeoutError, urllib.error.URLError):
                time.sleep(3)
                continue
        return None, None

    # ---------- phases ----------

    def auth(self):
        self.phase("auth", 0)
        code, me = self.api("GET", "/users/@me")
        if code != 200:
            raise RuntimeError(f"Token invalid (HTTP {code}). Grab a fresh one and try again.")
        self.log(f"Authenticated as: {me['username']} ({me['id']})")
        self.log(f"MFA enabled: {me.get('mfa_enabled')}  "
                 f"{'(good)' if me.get('mfa_enabled') else '(enable this in User Settings)'}")
        return me["id"]

    def sweep_dms(self, my_id):
        """Scan every DM channel, not just friends. Non-friends can also
        receive compromise DMs — the bot DMs anyone it can reach, not
        just people the user has added as friends."""
        self.phase("DM sweep", 10)
        # Union of friends (type=1 relationships) + all current DM
        # recipients (type=1 channels). We POST-open friends to make
        # sure their channel exists; non-friends are already in /channels
        # if there's any history.
        code, rels = self.api("GET", "/users/@me/relationships")
        friend_uids = [(r["user"]["username"], r["user"]["id"])
                       for r in rels if r.get("type") == 1] if code == 200 else []
        code2, chans = self.api("GET", "/users/@me/channels")
        dm_targets = {}  # uid -> (name, source-channel-or-None)
        if code2 == 200 and chans:
            for c in chans:
                if c.get("type") != 1:
                    continue
                for r in c.get("recipients", []):
                    if r.get("id"):
                        dm_targets[r["id"]] = (
                            r.get("username", "?"), c["id"])
        # Add friends we don't have a channel for yet (POST-opens them)
        for uname, uid in friend_uids:
            if uid not in dm_targets:
                dm_targets[uid] = (uname, None)
        self.log(f"Friends: {len(friend_uids)}  "
                 f"DM channels: {sum(1 for v in dm_targets.values() if v[1])}  "
                 f"total unique recipients: {len(dm_targets)}")
        hits = []
        all_targets = list(dm_targets.items())
        for i, (uid, (uname, pre_cid)) in enumerate(all_targets, 1):
            if pre_cid is None:
                code, chan = self.api("POST", "/users/@me/channels",
                                      data={"recipient_id": uid})
                if code != 200 or not chan:
                    self._sleep()
                    continue
                cid = chan["id"]
            else:
                cid = pre_cid
            before = None
            while True:
                path = f"/channels/{cid}/messages?limit=100"
                if before:
                    path += f"&before={before}"
                code2, msgs = self.api("GET", path)
                if code2 != 200 or not msgs:
                    break
                stop = False
                for m in msgs:
                    if int(m["id"]) < self.min_sf:
                        stop = True
                        break
                    if is_compromise_message(my_id, m, self.min_sf, self.max_sf):
                        hits.append((uname, cid, m["id"],
                                     (m.get("content") or "")[:60]))
                        self.log(f"  HIT {uname}  mid={m['id']}  "
                                 f":: {(m.get('content','') or '')[:60]!r}")
                if stop:
                    break
                before = msgs[-1]["id"]
                time.sleep(0.6 + random.random() * 0.3)
            if i % 10 == 0:
                self.phase("DM sweep", 10 + int(30 * i / len(all_targets)))
            self._sleep()
        self.log(f"DM compromise hits: {len(hits)}")
        if not self.go:
            return len(hits)
        for uname, cid, mid, snippet in hits:
            code, _ = self.api("DELETE", f"/channels/{cid}/messages/{mid}")
            if code == 204:
                self.audit.append({"action": "delete_dm", "user": uname,
                                   "channel": cid, "message": mid, "snippet": snippet,
                                   "ts": datetime.now(timezone.utc).isoformat()})
                self.log(f"  deleted DM to {uname}")
            self._sleep()
        return len(hits)

    def sweep_group_dms(self, my_id):
        self.phase("group DM sweep", 40)
        code, chans = self.api("GET", "/users/@me/channels")
        if code != 200:
            return 0
        gdms = [c for c in chans if c.get("type") == 3]
        self.log(f"Group DMs: {len(gdms)}")
        hits = []
        for c in gdms:
            cid = c["id"]
            name = c.get("name") or ",".join(r.get("username", "?")
                                             for r in c.get("recipients", []))[:40]
            before = None
            while True:
                path = f"/channels/{cid}/messages?limit=100"
                if before:
                    path += f"&before={before}"
                code2, msgs = self.api("GET", path)
                if code2 != 200 or not msgs:
                    break
                stop = False
                for m in msgs:
                    if int(m["id"]) < self.min_sf:
                        stop = True
                        break
                    if is_compromise_message(my_id, m, self.min_sf, self.max_sf):
                        hits.append((name, cid, m["id"]))
                        self.log(f"  HIT GDM:{name}  mid={m['id']}")
                if stop:
                    break
                before = msgs[-1]["id"]
                time.sleep(0.6)
            self._sleep()
        if not self.go:
            return len(hits)
        for name, cid, mid in hits:
            code, _ = self.api("DELETE", f"/channels/{cid}/messages/{mid}")
            if code == 204:
                self.audit.append({"action": "delete_gdm", "group": name,
                                   "channel": cid, "message": mid,
                                   "ts": datetime.now(timezone.utc).isoformat()})
                self.log(f"  deleted in GDM:{name}")
            self._sleep()
        return len(hits)

    def report_group_dm_departures(self, my_id):
        self.phase("group DM departures", 48)
        code, chans = self.api("GET", "/users/@me/channels")
        if code != 200:
            return 0
        gdms = [c for c in chans if c.get("type") == 3]
        reported = 0
        for c in gdms:
            if my_id in {r["id"] for r in c.get("recipients", [])}:
                continue
            cid = c["id"]
            gname = c.get("name") or ",".join(r.get("username", "?")
                                              for r in c.get("recipients", []))[:40]
            latest = None
            before = None
            for _ in range(3):
                path = f"/channels/{cid}/messages?limit=100"
                if before:
                    path += f"&before={before}"
                code2, msgs = self.api("GET", path)
                if code2 != 200 or not msgs:
                    break
                for m in msgs:
                    if m.get("type") != 2:
                        continue
                    mentions = m.get("mentions") or []
                    if mentions and mentions[0].get("id") == my_id:
                        latest = m
                        break
                if latest:
                    break
                before = msgs[-1]["id"]
                time.sleep(0.5)
            if not latest:
                self.log(f"  left {gname!r} (no event visible)")
                continue
            when_sf = int(latest["id"])
            when_iso = datetime.fromtimestamp(
                ((when_sf >> 22) + DISCORD_EPOCH) / 1000, tz=timezone.utc).isoformat()
            who = latest["author"]["id"]
            who_name = latest["author"].get("username", "?")
            self_remove = who == my_id
            suspicious = self_remove and (self.min_sf <= when_sf <= self.max_sf)
            tag = "  <-- compromise window" if suspicious else ""
            self.log(f"  left {gname!r} at {when_iso} by {who_name} "
                     f"(self={self_remove}){tag}")
            reported += 1
        if reported == 0:
            self.log("  no visible left-groups")
        return reported

    def sweep_guild_events(self, my_id):
        self.phase("guild events", 55)
        code, gs = self.api("GET", "/users/@me/guilds")
        if code != 200:
            return 0
        self.log(f"Guilds: {len(gs)}")
        hits = []
        for i, g in enumerate(gs, 1):
            code, events = self.api(
                "GET", f"/guilds/{g['id']}/scheduled-events?with_user_count=true")
            if code == 200 and isinstance(events, list):
                for ev in events:
                    if is_compromise_event(my_id, ev):
                        hits.append((g["name"], g["id"], ev["id"],
                                     ev.get("name", ""),
                                     ev.get("entity_metadata", {}).get("location", "")))
                        self.log(f"  HIT event in {g['name']}: "
                                 f"{ev.get('name','')!r}")
            if i % 15 == 0:
                self.phase("guild events", 55 + int(10 * i / len(gs)))
            self._sleep()
        if not self.go:
            return len(hits)
        for gname, gid, eid, ename, elocation in hits:
            code, _ = self.api("DELETE", f"/guilds/{gid}/scheduled-events/{eid}")
            if code == 204:
                self.audit.append({"action": "delete_event", "guild": gname,
                                   "event": eid, "name": ename, "location": elocation,
                                   "ts": datetime.now(timezone.utc).isoformat()})
                self.log(f"  deleted event in {gname}: {ename!r}")
            self._sleep()
        return len(hits)

    def sweep_guild_messages(self, my_id):
        self.phase("guild messages", 70)
        code, gs = self.api("GET", "/users/@me/guilds")
        if code != 200:
            return 0
        hits = []
        denied = 0
        for i, g in enumerate(gs, 1):
            qs = urllib.parse.urlencode({
                "author_id": my_id, "min_id": str(self.min_sf),
                "offset": 0, "include_nsfw": "true"})
            code, data = self.api(
                "GET", f"/guilds/{g['id']}/messages/search?{qs}")
            if code != 200 or not isinstance(data, dict):
                denied += 1
                self._sleep()
                continue
            for group in data.get("messages", []):
                if not group:
                    continue
                m = group[0]
                if is_compromise_message(my_id, m, self.min_sf, self.max_sf):
                    hits.append((g["name"], m["channel_id"], m["id"]))
                    self.log(f"  HIT guild {g['name']}  mid={m['id']}")
            if i % 15 == 0:
                self.phase("guild messages", 70 + int(15 * i / len(gs)))
            self._sleep()
        if not self.go:
            return len(hits)
        for gname, cid, mid in hits:
            code, _ = self.api("DELETE", f"/channels/{cid}/messages/{mid}")
            if code == 204:
                self.audit.append({"action": "delete_guild_msg", "guild": gname,
                                   "channel": cid, "message": mid,
                                   "ts": datetime.now(timezone.utc).isoformat()})
                self.log(f"  deleted guild message in {gname}")
            self._sleep()
        return len(hits)

    def cleanup_relationships(self):
        """Unblock, cancel outgoing friend requests, unignore.

        Important: non-friends can be ignored too (via Discord's "Ignore
        messages" per-DM toggle). The relationships endpoint only knows
        about friends/blocks/requests, so non-friend ignores are
        invisible via that path. We fix this by also iterating every DM
        channel and blindly calling the unignore endpoint on each
        recipient — Discord returns 204 on no-ops. Idempotent and safe.
        """
        self.phase("relationships", 90)
        code, rels = self.api("GET", "/users/@me/relationships")
        if code != 200:
            return 0
        blocked = [(r["user"]["username"], r["user"]["id"])
                   for r in rels if r.get("type") == 2]
        outgoing = [(r["user"]["username"], r["user"]["id"])
                    for r in rels if r.get("type") == 4]
        # friend-ignores (surfaced on relationship object)
        friend_ignored = [(r["user"]["username"], r["user"]["id"])
                          for r in rels if r.get("user_ignored")]
        # all DM recipients (friends AND non-friends; covers DM-level ignore
        # state that doesn't appear on relationships at all).
        code2, chans = self.api("GET", "/users/@me/channels")
        all_dm_recipients = []
        if code2 == 200 and chans:
            friend_ids_already_covered = {uid for _, uid in friend_ignored}
            for c in chans:
                if c.get("type") != 1:
                    continue
                for r in c.get("recipients", []):
                    if r.get("id") and r["id"] not in friend_ids_already_covered:
                        all_dm_recipients.append(
                            (r.get("username", "?"), r["id"]))

        self.log(f"blocked: {len(blocked)}  outgoing-reqs: {len(outgoing)}")
        self.log(f"friend-ignored: {len(friend_ignored)}  "
                 f"non-friend DM recipients to clear: {len(all_dm_recipients)}")
        if not self.go:
            return 0
        total = 0
        for group, action, path_tmpl in [
            (blocked, "unblock", "/users/@me/relationships/{uid}"),
            (outgoing, "cancel_outgoing", "/users/@me/relationships/{uid}"),
            (friend_ignored, "unignore_friend",
             "/users/@me/relationships/{uid}/ignore"),
            (all_dm_recipients, "unignore_dm",
             "/users/@me/relationships/{uid}/ignore"),
        ]:
            for uname, uid in group:
                code, _ = self.api("DELETE", path_tmpl.format(uid=uid))
                if code == 204:
                    total += 1
                    self.audit.append({"action": action, "user": uname, "id": uid,
                                       "ts": datetime.now(timezone.utc).isoformat()})
                    # Only log friend-ignores by name; DM blanket-clears
                    # are noisy, log just a count update at the end.
                    if action != "unignore_dm":
                        self.log(f"  {action} {uname}")
                self._sleep()
        if all_dm_recipients:
            self.log(f"  (also blanket-cleared ignore state on "
                     f"{len(all_dm_recipients)} non-friend DMs)")
        return total

    def run(self, phases):
        """phases: list of 'dms','gdms','gdm_departures','events','guild_msgs','rels'"""
        my_id = self.auth()
        totals = {}
        if "dms" in phases:
            totals["dms"] = self.sweep_dms(my_id)
        if "gdms" in phases:
            totals["gdms"] = self.sweep_group_dms(my_id)
        if "gdm_departures" in phases:
            totals["gdm_departures"] = self.report_group_dm_departures(my_id)
        if "events" in phases:
            totals["events"] = self.sweep_guild_events(my_id)
        if "guild_msgs" in phases:
            totals["guild_msgs"] = self.sweep_guild_messages(my_id)
        if "rels" in phases:
            totals["rels"] = self.cleanup_relationships()
        self.phase("done", 100)
        return totals


# ---------- utilities ----------

def to_snowflake(dt: datetime) -> int:
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH) << 22


# ---------- GUI ----------

def launch_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext

    root = tk.Tk()
    root.title("Discord Compromise Cleanup")
    root.geometry("760x720")

    PHASE_IDS = [
        ("dms", "DMs (every friend)"),
        ("gdms", "Group DMs"),
        ("gdm_departures", "Group DM departures (report only)"),
        ("events", "Server scheduled events"),
        ("guild_msgs", "Server messages"),
        ("rels", "Unblock / unignore / cancel reqs"),
    ]

    # ---- top warning banner ----
    banner = tk.Frame(root, bg="#8a1b1b", padx=10, pady=8)
    banner.pack(fill="x")
    tk.Label(banner, bg="#8a1b1b", fg="white", justify="left",
             font=("Segoe UI", 10, "bold"),
             text="⚠  Using a user token to automate Discord actions violates "
                  "Discord's Terms of Service.").pack(anchor="w")
    tk.Label(banner, bg="#8a1b1b", fg="white", justify="left",
             font=("Segoe UI", 9),
             text="Change your password + enable 2FA + revoke Authorized Apps + "
                  "log out all devices BEFORE running this.").pack(anchor="w")

    main = ttk.Frame(root, padding=10)
    main.pack(fill="both", expand=True)

    # ---- token ----
    tframe = ttk.LabelFrame(main, text="1. Discord User Token", padding=8)
    tframe.pack(fill="x")

    def how_to_get_token():
        messagebox.showinfo(
            "How to grab your token",
            "You MUST use the Discord web app (discord.com/app). The desktop "
            "client disables DevTools.\n\n"
            "1. Log into discord.com/app with your NEW password.\n"
            "2. Press Ctrl+Shift+I to open DevTools.\n"
            "3. Click the Network tab, filter the list by typing /api\n"
            "4. In Discord, click any server or channel. API requests will "
            "appear in the Network tab.\n"
            "5. Click any /api/v9/... request. Scroll to Request Headers.\n"
            "6. Find 'Authorization:' and copy its value.\n"
            "7. Paste it into the field above.\n\n"
            "Ignore Discord's red 'STOP!' warning in the Console — that is for "
            "people being tricked by scammers. You are not being scammed.")

    token_var = tk.StringVar()
    row = ttk.Frame(tframe)
    row.pack(fill="x")
    token_entry = ttk.Entry(row, textvariable=token_var, show="•", width=55)
    token_entry.pack(side="left", padx=(0, 6))
    ttk.Button(row, text="How?", command=how_to_get_token, width=8).pack(side="left")
    ttk.Button(row, text="Load from file...",
               command=lambda: load_token_file()).pack(side="left", padx=(6, 0))

    def load_token_file():
        p = filedialog.askopenfilename(title="Pick a text file containing your token")
        if not p:
            return
        try:
            token_var.set(Path(p).read_text().strip())
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---- window ----
    wframe = ttk.LabelFrame(main, text="2. Compromise window (UTC)", padding=8)
    wframe.pack(fill="x", pady=(8, 0))

    now = datetime.now(timezone.utc)
    start_var = tk.StringVar(
        value=(now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M"))
    end_var = tk.StringVar(value=now.strftime("%Y-%m-%d %H:%M"))

    r = ttk.Frame(wframe); r.pack(fill="x")
    ttk.Label(r, text="Start:").pack(side="left")
    ttk.Entry(r, textvariable=start_var, width=20).pack(side="left", padx=(4, 12))
    ttk.Label(r, text="End:").pack(side="left")
    ttk.Entry(r, textvariable=end_var, width=20).pack(side="left", padx=(4, 0))
    ttk.Label(wframe,
              text="Format: YYYY-MM-DD HH:MM (UTC). Default is the last 24h.",
              foreground="#555").pack(anchor="w", pady=(4, 0))

    # ---- phases ----
    pframe = ttk.LabelFrame(main, text="3. What to clean", padding=8)
    pframe.pack(fill="x", pady=(8, 0))
    phase_vars = {}
    for pid, label in PHASE_IDS:
        v = tk.BooleanVar(value=True)
        phase_vars[pid] = v
        ttk.Checkbutton(pframe, text=label, variable=v).pack(anchor="w")

    # ---- pace ----
    pace_var = tk.DoubleVar(value=2.5)
    pr = ttk.Frame(main); pr.pack(fill="x", pady=(8, 0))
    ttk.Label(pr, text="API pacing (seconds between calls, higher = safer):"
              ).pack(side="left")
    ttk.Spinbox(pr, from_=1.0, to=10.0, increment=0.5, textvariable=pace_var,
                width=6).pack(side="left", padx=(6, 0))

    # ---- action buttons ----
    aframe = ttk.Frame(main); aframe.pack(fill="x", pady=(10, 0))
    scan_btn = ttk.Button(aframe, text="Scan (dry run — don't delete anything)")
    scan_btn.pack(side="left")
    exec_btn = ttk.Button(aframe, text="Delete (execute)")
    exec_btn.pack(side="left", padx=(8, 0))

    # ---- log + progress ----
    pbar = ttk.Progressbar(main, mode="determinate", maximum=100)
    pbar.pack(fill="x", pady=(10, 0))
    status_var = tk.StringVar(value="Ready.")
    ttk.Label(main, textvariable=status_var, foreground="#333").pack(anchor="w")
    log = scrolledtext.ScrolledText(main, height=14, font=("Consolas", 9))
    log.pack(fill="both", expand=True, pady=(6, 0))
    log.configure(state="disabled")

    msg_queue = queue.Queue()

    def dispatch_queue():
        try:
            while True:
                evt = msg_queue.get_nowait()
                tag = evt[0]
                if tag == "log":
                    log.configure(state="normal")
                    log.insert("end", evt[1] + "\n")
                    log.see("end")
                    log.configure(state="disabled")
                elif tag == "phase":
                    status_var.set(f"{evt[1]}…")
                    pbar["value"] = evt[2]
                elif tag == "done":
                    scan_btn["state"] = "normal"
                    exec_btn["state"] = "normal"
                    status_var.set(evt[1])
                    pbar["value"] = 100
                elif tag == "error":
                    scan_btn["state"] = "normal"
                    exec_btn["state"] = "normal"
                    status_var.set("Error.")
                    messagebox.showerror("Error", evt[1])
        except queue.Empty:
            pass
        root.after(100, dispatch_queue)

    def parse_window():
        s = datetime.strptime(start_var.get().strip(), "%Y-%m-%d %H:%M")
        e = datetime.strptime(end_var.get().strip(), "%Y-%m-%d %H:%M")
        return s.replace(tzinfo=timezone.utc), e.replace(tzinfo=timezone.utc)

    def validate():
        token = token_var.get().strip()
        if not token:
            messagebox.showerror("Missing", "Paste your Discord user token first.")
            return None
        try:
            s, e = parse_window()
        except ValueError:
            messagebox.showerror(
                "Window", "Window must be formatted as YYYY-MM-DD HH:MM")
            return None
        if e <= s:
            messagebox.showerror("Window", "End must be after Start.")
            return None
        phases = [pid for pid, v in phase_vars.items() if v.get()]
        if not phases:
            messagebox.showerror("Nothing", "Pick at least one phase.")
            return None
        return token, s, e, phases, pace_var.get()

    def run_in_thread(go: bool):
        v = validate()
        if not v:
            return
        token, s, e, phases, pace = v
        min_sf = to_snowflake(s)
        max_sf = to_snowflake(e)
        if go:
            if not messagebox.askyesno(
                    "Confirm delete",
                    "This will actually DELETE matching messages, events, "
                    "and clear relationship states.\n\n"
                    "Dry-run first if you haven't. Proceed?"):
                return
        log.configure(state="normal"); log.delete("1.0", "end")
        log.configure(state="disabled")
        scan_btn["state"] = "disabled"
        exec_btn["state"] = "disabled"
        pbar["value"] = 0

        def progress_cb(evt):
            msg_queue.put(evt)

        def worker():
            try:
                engine = Cleanup(token, min_sf, max_sf, pace=pace, go=go,
                                 progress=progress_cb)
                totals = engine.run(phases)
                summary = "  ".join(f"{k}={v}" for k, v in totals.items())
                if go and engine.audit:
                    auditp = Path.cwd() / "discord-cleanup-audit.json"
                    auditp.write_text(json.dumps(engine.audit, indent=2))
                    msg_queue.put(("log", f"Audit log saved to {auditp}"))
                mode = "DELETED" if go else "DRY-RUN"
                msg_queue.put(("done", f"{mode} complete. {summary}"))
            except SystemExit:
                msg_queue.put(("done",
                               "Discord revoked the token. Stop, grab a new "
                               "token, and re-run."))
            except Exception as ex:
                msg_queue.put(("error", f"{type(ex).__name__}: {ex}"))

        threading.Thread(target=worker, daemon=True).start()

    scan_btn.configure(command=lambda: run_in_thread(False))
    exec_btn.configure(command=lambda: run_in_thread(True))

    dispatch_queue()
    root.mainloop()


# ---------- CLI ----------

def cli():
    ap = argparse.ArgumentParser(description="Discord compromise cleanup")
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--window-start", default=None)
    ap.add_argument("--window-end", default=None)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--pace", type=float, default=2.5)
    ap.add_argument("--phase", action="append", default=None,
                    choices=["dms", "gdms", "gdm_departures", "events",
                             "guild_msgs", "rels"])
    args = ap.parse_args()
    token = Path(args.token_file).expanduser().read_text().strip()
    now = datetime.now(timezone.utc)
    end = (datetime.fromisoformat(args.window_end.replace("Z", "+00:00"))
           if args.window_end else now)
    start = (datetime.fromisoformat(args.window_start.replace("Z", "+00:00"))
             if args.window_start else end - timedelta(hours=24))
    print(f"window: {start.isoformat()}  ..  {end.isoformat()}")
    print(f"mode:   {'DELETE' if args.go else 'DRY-RUN'}")
    phases = args.phase or ["dms", "gdms", "gdm_departures", "events",
                            "guild_msgs", "rels"]
    def progress(evt):
        if evt[0] == "log":
            print(evt[1])
        elif evt[0] == "phase":
            print(f"-- {evt[1]} --")
    engine = Cleanup(token, to_snowflake(start), to_snowflake(end),
                     pace=args.pace, go=args.go, progress=progress)
    totals = engine.run(phases)
    print("\nSummary:", totals)
    if args.go and engine.audit:
        p = Path("./discord-cleanup-audit.json")
        p.write_text(json.dumps(engine.audit, indent=2))
        print(f"Audit log: {p}")


# ---------- entry ----------

if __name__ == "__main__":
    if "--cli" in sys.argv or "--help" in sys.argv or "-h" in sys.argv:
        if "--cli" in sys.argv:
            sys.argv.remove("--cli")
        cli()
    else:
        try:
            launch_gui()
        except Exception as e:
            # Tkinter missing or display not available — fall back to help
            print(f"Could not launch GUI: {e}", file=sys.stderr)
            print("For CLI mode: python3 discord-compromise-cleanup.py --cli "
                  "--token-file ~/.discord-token [--go]", file=sys.stderr)
            sys.exit(1)
