"""Simulated smart-home device gated by the APPROVED YOG policy. In memory; one instance per process."""
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.core import facts
from app.engine.adapter import EngineAdapter


class DeviceError(ValueError):
    """Bad tool name / arguments (a client error, not a policy decision)."""


class NoPolicyError(RuntimeError):
    """No approved policy exists: the simulator refuses to run ungoverned."""


class DeviceState(BaseModel):
    doors: dict[str, str] = Field(default_factory=lambda: {"front_door": "locked", "back_door": "locked", "garage_door": "locked"})
    thermostats: dict[str, int] = Field(default_factory=lambda: {"living_room": 21, "bedroom": 19})
    valves: dict[str, int] = Field(default_factory=lambda: {"water_main": 0, "garden_tap": 0})


class Clock(BaseModel):
    hour: int = 14
    day: str = "mon"


class LogEntry(BaseModel):
    n: int
    at: str
    sim_hour: int
    sim_day: str
    tool: str
    args: dict
    guarded: bool
    decision: str                 # ALLOW | DENY | UNGUARDED
    reason: str
    executed: bool
    message: str
    facts: list[str]
    trace: list[str] = Field(default_factory=list)


TOOLS = {
    "unlock_door": ["door_id", "pin"],
    "lock_door": ["door_id"],
    "set_thermostat": ["zone", "temperature"],
    "open_valve": ["valve_id", "percent"],
    "get_status": ["device_id"],
}
DAYS = facts.DAYS


class DeviceSim:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = DeviceState()
        self.clock = Clock()
        self.log: list[LogEntry] = []

    def set_clock(self, hour: int, day: str) -> Clock:
        if not 0 <= hour <= 23:
            raise DeviceError("hour must be 0-23")
        if day not in DAYS:
            raise DeviceError(f"day must be one of {', '.join(DAYS)}")
        self.clock = Clock(hour=hour, day=day)
        return self.clock

    # ---- applying a command to device state -------------------------------------------
    def _validate(self, tool: str, args: dict) -> dict:
        if tool not in TOOLS:
            raise DeviceError(f"unknown tool '{tool}'. Known: {', '.join(TOOLS)}")
        a = {k: v for k, v in args.items() if k in TOOLS[tool]}
        optional = {"unlock_door": {"pin"}, "open_valve": {"percent"}}.get(tool, set())
        need = [k for k in TOOLS[tool] if k not in optional]
        for k in need:
            if k not in a:
                raise DeviceError(f"{tool} needs argument '{k}'")
        s = self.state
        if tool in ("unlock_door", "lock_door") and facts.ident(a["door_id"]) not in s.doors:
            raise DeviceError(f"unknown door '{a['door_id']}'. Known: {', '.join(s.doors)}")
        if tool == "set_thermostat":
            if facts.ident(a["zone"]) not in s.thermostats:
                raise DeviceError(f"unknown zone '{a['zone']}'. Known: {', '.join(s.thermostats)}")
            if not isinstance(a["temperature"], (int, float)) or isinstance(a["temperature"], bool):
                raise DeviceError("temperature must be a number")
        if tool == "open_valve":
            if facts.ident(a["valve_id"]) not in s.valves:
                raise DeviceError(f"unknown valve '{a['valve_id']}'. Known: {', '.join(s.valves)}")
            if not isinstance(a.get("percent", 100), (int, float)) or isinstance(a.get("percent", 100), bool):
                raise DeviceError("percent must be a number")
            a.setdefault("percent", 100)
        if tool == "get_status" and not isinstance(a["device_id"], str):
            raise DeviceError("device_id must be text")
        return a

    def _apply(self, tool: str, a: dict) -> str:
        s = self.state
        if tool == "unlock_door":
            s.doors[facts.ident(a["door_id"])] = "unlocked"
            return f"{facts.ident(a['door_id'])} is now unlocked"
        if tool == "lock_door":
            s.doors[facts.ident(a["door_id"])] = "locked"
            return f"{facts.ident(a['door_id'])} is now locked"
        if tool == "set_thermostat":
            s.thermostats[facts.ident(a["zone"])] = int(round(a["temperature"]))
            return f"{facts.ident(a['zone'])} set to {int(round(a['temperature']))} C"
        if tool == "open_valve":
            s.valves[facts.ident(a["valve_id"])] = int(round(a["percent"]))
            return f"{facts.ident(a['valve_id'])} opened to {int(round(a['percent']))}%"
        d = facts.ident(a["device_id"])
        return f"status of {d}: door={s.doors.get(d)}, valve={s.valves.get(d)}, thermostat={s.thermostats.get(d)}"

    # ---- the gate ---------------------------------------------------------------------
    def command(self, tool: str, args: dict, adapter: EngineAdapter, policy: str | None, guard: bool = True,
                actor: str = "agent") -> LogEntry:
        a = self._validate(tool, args)
        ctx = facts.facts_from_call(tool, a, self.clock.hour, self.clock.day)
        resource = next((facts.ident(v) for v in a.values() if isinstance(v, str)), "item")
        if guard:
            if policy is None:
                raise NoPolicyError("no approved policy: approve a policy on the Review page first")
            r = adapter.check(policy, actor, "can_" + facts.ident(tool), resource, ctx)
            decision, reason, trace = r.decision, r.reason, r.trace
        else:
            decision, reason, trace = "UNGUARDED", "guard is switched off: the command runs without any policy check", []
        executed = decision in ("ALLOW", "UNGUARDED")
        message = self._apply(tool, a) if executed else f"BLOCKED by YOG: device unchanged ({reason})"
        entry = LogEntry(n=len(self.log) + 1, at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         sim_hour=self.clock.hour, sim_day=self.clock.day, tool=tool, args=a, guarded=guard,
                         decision=decision, reason=reason, executed=executed, message=message, facts=ctx, trace=trace)
        self.log.append(entry)
        return entry


# The scripted "demo agent": what an LLM agent might ask for during a day. Hours are simulated.
DEMO_SCRIPT: list[dict] = [
    {"hour": 14, "day": "mon", "tool": "unlock_door", "args": {"door_id": "front_door"}, "why": "afternoon: allowed"},
    {"hour": 14, "day": "mon", "tool": "set_thermostat", "args": {"zone": "living_room", "temperature": 22}, "why": "within 16-28"},
    {"hour": 14, "day": "mon", "tool": "set_thermostat", "args": {"zone": "living_room", "temperature": 35}, "why": "too hot"},
    {"hour": 14, "day": "mon", "tool": "open_valve", "args": {"valve_id": "garden_tap", "percent": 80}, "why": "more than 50%"},
    {"hour": 3, "day": "tue", "tool": "unlock_door", "args": {"door_id": "front_door"}, "why": "3am: the headline moment"},
    {"hour": 23, "day": "tue", "tool": "unlock_door", "args": {"door_id": "back_door"}, "why": "11pm"},
    {"hour": 9, "day": "wed", "tool": "lock_door", "args": {"door_id": "front_door"}, "why": "locking is fine"},
]
