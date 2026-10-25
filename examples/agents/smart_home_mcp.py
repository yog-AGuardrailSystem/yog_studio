"""Smart-home MCP server: the headline demo agent for YOG Studio."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("smart-home")

# Fake in-memory device state (the real simulator lives in Studio).
DOORS = {"front_door": "locked", "back_door": "locked"}
THERMOSTATS = {"living_room": 21.0}
VALVES = {"water_main": 0}


@mcp.tool()
def unlock_door(door_id: str, pin: str | None = None) -> str:
    """Unlock a door. Optionally supply a PIN."""
    DOORS[door_id] = "unlocked"
    return f"{door_id} unlocked"


@mcp.tool()
def lock_door(door_id: str) -> str:
    """Lock a door."""
    DOORS[door_id] = "locked"
    return f"{door_id} locked"


@mcp.tool()
def set_thermostat(zone: str, temperature: float) -> str:
    """Set the target temperature (Celsius) for a zone."""
    THERMOSTATS[zone] = temperature
    return f"{zone} set to {temperature}"


@mcp.tool()
async def open_valve(valve_id: str, percent: int = 100) -> str:
    """Open a valve to the given percentage."""
    VALVES[valve_id] = percent
    return f"{valve_id} at {percent}%"


@mcp.tool()
def get_status(device_id: str) -> dict:
    """Read-only: report the state of a device."""
    return {"door": DOORS.get(device_id), "valve": VALVES.get(device_id)}


if __name__ == "__main__":
    mcp.run()
