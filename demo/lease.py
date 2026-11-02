"""Who may act in the demo: one session is in control at a time, the others wait in line. A sign-in takes the
flat when it is free, else a place in line. Pure logic with an injectable clock (tests); the plug-in persists it
in DEMO_STATE_DIR so a reset (a restart) keeps everyone in.
Every session carries its network (a hash of its IPv4 /24 or IPv6 /48): one turn or place in line per network,
and a network that just had a turn waits COOL_S while others want one."""
import hashlib
import json
import os
import secrets
import threading
import time

LEASE_S = 15 * 60        # the longest turn
IDLE_S = 3 * 60          # a turn ends after this long without an action
HEARTBEAT_S = 30         # a tab that said goodbye (closed) and did not beat again frees control after this
# a tab that is only hidden (an app switch, a locked screen) beats no more but keeps control until IDLE_S
GONE_S = 10 * 60         # a session out of turn and not seen this long is signed out
SHORT_S = 30             # a turn this short with no action leaves nothing to reset
TAKE_GAP_S = 2 * 60      # one "get in line again" per session in this time
COOL_S = 15 * 60         # after a turn, its bucket waits this long while others are in line
RESET_GAP_S = 2 * 60     # at most one reset in this time
MAX_SESSIONS = 300
MAX_LINE = 20            # places in line of tabs that beat lately: a silent one keeps its place but fills none
LIVE_S = 3 * HEARTBEAT_S


class Refused(Exception):
    """A request the lease turns down: `why` for the guest, `wait_s` when trying later helps, `code` the HTTP status."""
    def __init__(self, why, wait_s=0, code=409):
        super().__init__(why)
        self.why, self.wait_s, self.code = why, int(wait_s), code


def _h(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


class Lease:
    def __init__(self, path=None, clock=time.time):
        self.path, self.clock, self.lock = path, clock, threading.RLock()
        self.sessions: dict = {}     # token hash -> {"seen": t, "ip": bucket, "took": t of the last take}
        self.ctl, self.since, self.act, self.acted = None, 0.0, 0.0, False
        self.reset_used = False      # the guest in control reset once this turn
        self.queue: list = []        # token hashes waiting for control, in order
        self.cool: dict = {}         # bucket -> until when it waits while others want a turn
        self.reset_due = ""          # why the last turn ended, until the restart after its reset (reset_finished)
        self.resetting = ""          # a reset runs: "asked" the simulator, "clean" when it answered; "" none
        self.last_reset = 0.0
        self.turn: dict = {"actions": 0, "rules": 0}      # what the guest in control did this turn
        self.summaries: dict = {}    # token hash -> the end-of-session summary of its last turn, until it is read
        self._load()

    # ---- persistence: hashes only, never a token ----
    _KEEP = ("ctl", "since", "act", "acted", "reset_used", "queue", "cool", "reset_due", "resetting", "last_reset", "turn",
             "summaries")

    def _load(self):
        try:
            d = json.loads(open(self.path, encoding="utf-8").read()) if self.path else {}
        except (OSError, ValueError):
            d = {}
        self.sessions = {k: v for k, v in (d.get("sessions") or {}).items() if isinstance(v, dict)}
        for k in self._KEEP:
            if k in d:
                setattr(self, k, d[k])
        self.queue = [q for q in self.queue if q in self.sessions]
        if self.ctl not in self.sessions:
            self.ctl = None

    def _save(self):
        if not self.path:
            return
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sessions": self.sessions, **{k: getattr(self, k) for k in self._KEEP}}, f)
        os.replace(tmp, self.path)

    # ---- sessions ----
    def login(self, net: str = "") -> str:
        """A new session that takes the flat when it is free, else a place in line (Refused: neither, no session).
        When full, the longest idle session out of turn goes: never the controller, one in line or one whose tab
        beat in the last HEARTBEAT_S (then the demo is full: Refused)."""
        with self.lock:
            self.tick()
            self._may_join(net)
            if len(self.sessions) >= MAX_SESSIONS:
                now = self.clock()
                idle = [k for k in self.sessions if k != self.ctl and k not in self.queue and now - self.sessions[k]["seen"] > HEARTBEAT_S]
                if not idle:
                    raise Refused("the demo is full: try later", 60, 503)
                self._drop(min(idle, key=lambda k: self.sessions[k]["seen"]))
            tok = secrets.token_urlsafe(32)
            h = _h(tok)
            self.sessions[h] = {"seen": self.clock(), "ip": net, "took": self.clock()}
            self._join(h)
            self._save()
            return tok

    def known(self, tok: str) -> bool:
        return _h(tok) in self.sessions

    def role(self, tok: str, method: str = "", path: str = "") -> "str | None":
        """view / control / None; an action of the controller (a change, steering the simulator; not a heartbeat,
        not a read) keeps the turn alive."""
        with self.lock:
            self.tick()
            h = _h(tok)
            if h not in self.sessions:
                return None
            if h != self.ctl:
                return "view"
            if method not in ("", "GET", "HEAD", "WS") and (not path.startswith("/api/demo/") or path.startswith("/api/demo/sim/")):
                self.act, self.acted = self.clock(), True
                self.turn["actions"] = self.turn.get("actions", 0) + 1
            return "control"

    def heartbeat(self, tok: str) -> bool:
        with self.lock:
            h = _h(tok)
            if h not in self.sessions:
                return False
            self.sessions[h]["seen"] = self.clock()
            return True

    def still(self, tok: str) -> dict:
        """The guest in control says "still here": the idle time starts again (the 15 minutes do not)."""
        with self.lock:
            if _h(tok) == self.ctl:
                self.act = self.clock()
                self._save()
            return self.view(tok)

    def logout(self, tok: str):
        with self.lock:
            self._drop(_h(tok))
            self._save()

    def _drop(self, h):
        if h == self.ctl:
            self._end("signed out")
        self.sessions.pop(h, None)
        if h in self.queue:
            self.queue.remove(h)

    # ---- control ----
    def take(self, tok: str) -> dict:
        """After a turn (or a lost place): the turn when the flat is free, else a place in line; Refused names why not."""
        with self.lock:
            self.tick()
            h, now = _h(tok), self.clock()
            s = self.sessions.get(h)
            if s is None or h == self.ctl or h in self.queue:
                return self.view(tok)
            if now - s.get("took", 0) < TAKE_GAP_S:
                raise Refused("you asked a moment ago: wait a little", TAKE_GAP_S - (now - s["took"]))
            self._may_join(s.get("ip", ""))
            s["took"] = now
            self._join(h)
            self._save()
            return self.view(tok)

    def _may_join(self, ip: str):
        """Refused when this network may not have the turn or a place in line now."""
        now = self.clock()
        mine = [k for k in [self.ctl, *self.queue] if k and self.sessions.get(k, {}).get("ip") == ip]
        if ip and mine:
            raise Refused("one turn or place in line per guest: you have one already")
        others = self.ctl is not None or bool(self.queue)
        if ip and others and self.cool.get(ip, 0) > now:
            raise Refused("you had a turn: others go first", self.cool[ip] - now)
        live = [q for q in self.queue if now - self.sessions.get(q, {}).get("seen", 0) <= LIVE_S]
        if len(live) >= MAX_LINE and (self.ctl is not None or self.reset_due):
            raise Refused("the line is full: try later", 60)

    def _join(self, h):
        if self.ctl is None and not self.queue and not self.reset_due:
            self._grant(h)
        else:
            self.queue.append(h)

    def leave(self, tok: str) -> dict:
        with self.lock:
            h = _h(tok)
            if h in self.queue:
                self.queue.remove(h)
                self._save()
            return self.view(tok)

    def release(self, tok: str) -> bool:
        with self.lock:
            if _h(tok) != self.ctl:
                return False
            self._end("released")
            self._save()
            return True

    def use_reset(self, tok: str):
        """The guest in control may reset once a turn, and not sooner than RESET_GAP_S after the last reset."""
        with self.lock:
            if _h(tok) != self.ctl:
                raise Refused("only the guest in control resets")
            if self.reset_used:
                raise Refused("one reset per turn")
            wait = self.last_reset + RESET_GAP_S - self.clock()
            if wait > 0:
                raise Refused("the flat was reset a moment ago", wait)
            self.reset_used, self.last_reset = True, self.clock()
            self.resetting = self.resetting or "asked"
            self._save()

    def note_rule(self):
        """A rule of the house fired: counted for the turn's summary."""
        with self.lock:
            if self.ctl is not None:
                self.turn["rules"] = self.turn.get("rules", 0) + 1

    def dismiss(self, tok: str):
        with self.lock:
            if self.summaries.pop(_h(tok), None) is not None:
                self._save()

    def _grant(self, h):
        now = self.clock()
        self.ctl, self.since, self.act, self.acted, self.reset_used = h, now, now, False, False
        self.turn = {"actions": 0, "rules": 0}
        self.summaries.pop(h, None)
        self.sessions[h]["seen"] = now

    def _end(self, why: str):
        """The turn ends; one that changed something (or lasted) leaves a reset due. The next in line gets the
        turn at once only when nothing is to be reset, else after the reset (the restart's first tick)."""
        if self.ctl is None:
            return
        now = self.clock()
        if self.acted or now - self.since >= SHORT_S:
            self.reset_due = why
        ip = self.sessions.get(self.ctl, {}).get("ip", "")
        if ip:
            self.cool[ip] = now + COOL_S
        if self.ctl in self.sessions:
            self.summaries[self.ctl] = {"why": why, "minutes": round((now - self.since) / 60, 1), **self.turn}
            if len(self.summaries) > MAX_SESSIONS:
                self.summaries.pop(next(iter(self.summaries)))
        self.ctl = None
        self._next()

    def bye(self, tok: str) -> bool:
        """The page is closing (its unload beacon): unless it beats again within HEARTBEAT_S, its turn or place ends."""
        with self.lock:
            s = self.sessions.get(_h(tok))
            if s is None:
                return False
            s["bye"] = self.clock()
            self._save()
            return True

    def _closed(self, h, now) -> bool:
        s = self.sessions.get(h) or {}
        return bool(s.get("bye")) and s["bye"] >= s.get("seen", 0) and now - s["bye"] >= HEARTBEAT_S

    def _gone(self, h, now) -> bool:
        """A session in line that cannot take its turn: its tab closed, or nothing heard of it for IDLE_S."""
        s = self.sessions.get(h) or {}
        return self._closed(h, now) or now - s.get("seen", 0) > IDLE_S

    def _next(self):
        if self.reset_due or self.ctl is not None:
            return
        now = self.clock()
        while self.queue:
            h = self.queue.pop(0)
            if h in self.sessions and not self._gone(h, now):
                self._grant(h)
                break

    def reset_wait(self) -> "float | None":
        """Seconds until a due reset may run (0: now); None when none is due."""
        with self.lock:
            if not self.reset_due:
                return None
            if self.resetting:
                return 0.0
            return max(0.0, self.last_reset + RESET_GAP_S - self.clock())

    def take_reset(self) -> str:
        """Why a turn ended, once its reset may run ("" = none, or not yet): the plug-in resets the house then.
        The turn stays due until the restart after the reset calls reset_finished: nobody gets the old flat."""
        with self.lock:
            if not self.reset_due or self.resetting or self.clock() - self.last_reset < RESET_GAP_S:
                return ""
            self.resetting, self.last_reset = "asked", self.clock()
            self._save()
            return self.reset_due

    def sim_clean(self):
        """The simulator answered the reset: the broker is clean, the restart need not ask again."""
        with self.lock:
            if self.resetting:
                self.resetting = "clean"
                self._save()

    def reset_finished(self) -> bool:
        """The backend started again on the pristine house after a reset: the next in line gets the flat.
        False when no reset was running."""
        with self.lock:
            if not self.resetting:
                return False
            self.resetting, self.reset_due = "", ""
            self._next()
            self._save()
            return True

    def tick(self) -> "str | None":
        """Ends the turn that is over (cap, idle, a closed tab), signs out the long gone, gives a free turn away."""
        with self.lock:
            now, why = self.clock(), None
            if self.ctl is not None:
                why = ("time is up" if now - self.since >= LEASE_S else "idle" if now - self.act >= IDLE_S
                       else "tab closed" if self._closed(self.ctl, now) else None)
                if why:
                    self._end(why)
            gone = [h for h, s in self.sessions.items() if h != self.ctl and now - s["seen"] >= GONE_S]
            for h in gone:
                self._drop(h)
            self.cool = {ip: t for ip, t in self.cool.items() if t > now}
            had = self.ctl
            self._next()
            if why or gone or had != self.ctl:
                self._save()
            return why

    def view(self, tok: str) -> dict:
        """What a session's page shows: its role, the turn's time left, its place in line and a worst-case wait."""
        with self.lock:
            now, h = self.clock(), _h(tok)
            left = max(0, int(self.since + LEASE_S - now)) if self.ctl else 0
            idle = max(0, int(self.act + IDLE_S - now)) if self.ctl else 0
            pos = self.queue.index(h) + 1 if h in self.queue else 0
            reset = self.reset_wait()
            eta = (left + (pos - 1) * LEASE_S + int(reset or 0)) if pos else 0
            return {"signed_in": h in self.sessions, "role": "control" if h == self.ctl else "view",
                    "busy": self.ctl is not None, "left_s": left, "idle_s": idle, "position": pos,
                    "eta_s": eta, "resetting": reset is not None, "can_reset": h == self.ctl and not self.reset_used,
                    "turn": dict(self.turn) if h == self.ctl else None, "summary": self.summaries.get(h),
                    "waiting": len(self.queue)}
