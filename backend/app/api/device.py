from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.api.policies import get_store
from app.device.simulator import (DEMO_SCRIPT, Clock, DeviceError, DeviceSim, DeviceState, LogEntry,
                                  NoPolicyError)
from app.engine.adapter import EngineAdapter, EngineError
from app.policies.store import PolicyStore

router = APIRouter(prefix="/device")


@lru_cache(maxsize=1)
def get_sim() -> DeviceSim:
    return DeviceSim()


class Snapshot(BaseModel):
    state: DeviceState
    clock: Clock
    log: list[LogEntry]
    policy_id: str | None


def _policy(store: PolicyStore, policy_id: str | None):
    """Only an APPROVED policy governs the device. None means: refuse to run guarded."""
    return store.get(policy_id) if policy_id else store.latest()


def _snap(sim: DeviceSim, store: PolicyStore, policy_id: str | None = None) -> Snapshot:
    rec = _policy(store, policy_id)
    return Snapshot(state=sim.state, clock=sim.clock, log=sim.log, policy_id=rec.id if rec else None)


@router.get("/state", response_model=Snapshot)
def state(sim: DeviceSim = Depends(get_sim), store: PolicyStore = Depends(get_store)) -> Snapshot:
    return _snap(sim, store)


class ClockReq(BaseModel):
    hour: int
    day: str


@router.post("/clock", response_model=Snapshot)
def set_clock(req: ClockReq, sim: DeviceSim = Depends(get_sim), store: PolicyStore = Depends(get_store)) -> Snapshot:
    try:
        sim.set_clock(req.hour, req.day)
    except DeviceError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _snap(sim, store)


@router.post("/reset", response_model=Snapshot)
def reset(sim: DeviceSim = Depends(get_sim), store: PolicyStore = Depends(get_store)) -> Snapshot:
    sim.reset()
    return _snap(sim, store)


class CommandReq(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    guard: bool = True
    policy_id: str | None = None


def _run(sim, adapter, store, tool, args, guard, policy_id) -> LogEntry:
    rec = _policy(store, policy_id)
    if guard and rec is None:
        raise HTTPException(status_code=409, detail="no approved policy: approve a policy on the Review page first")
    try:
        return sim.command(tool, args, adapter, rec.yog_source if rec else None, guard)
    except DeviceError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except NoPolicyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except EngineError as e:
        raise HTTPException(status_code=422, detail=f"approved policy cannot be evaluated: {e}")


@router.post("/command", response_model=LogEntry)
def command(req: CommandReq, sim: DeviceSim = Depends(get_sim), adapter: EngineAdapter = Depends(get_adapter),
            store: PolicyStore = Depends(get_store)) -> LogEntry:
    return _run(sim, adapter, store, req.tool, req.args, req.guard, req.policy_id)


class DemoReq(BaseModel):
    guard: bool = True
    policy_id: str | None = None


@router.post("/demo", response_model=Snapshot)
def demo(req: DemoReq, sim: DeviceSim = Depends(get_sim), adapter: EngineAdapter = Depends(get_adapter),
         store: PolicyStore = Depends(get_store)) -> Snapshot:
    """Resets the device, then replays the scripted agent day, setting the simulated clock before each step."""
    if req.guard and _policy(store, req.policy_id) is None:
        raise HTTPException(status_code=409, detail="no approved policy: approve a policy on the Review page first")
    sim.reset()
    for step in DEMO_SCRIPT:
        sim.set_clock(step["hour"], step["day"])
        _run(sim, adapter, store, step["tool"], step["args"], req.guard, req.policy_id)
    return _snap(sim, store, req.policy_id)
