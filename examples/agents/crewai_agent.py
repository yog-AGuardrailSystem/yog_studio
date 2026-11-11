"""CrewAI: tools are functions marked with @tool("name")."""
import subprocess

from crewai.tools import tool


@tool("run shell command")
def run_shell_command(command: str) -> str:
    """Run a shell command on the build server."""
    return subprocess.run(command, shell=True, capture_output=True, text=True).stdout


@tool("publish release")
def publish_release(version: str, channel: str = "beta") -> str:
    """Publish a release to a channel."""
    return f"published {version} to {channel}"


@tool("read build log")
def read_build_log(job: str) -> str:
    """Read the log of a build job."""
    return "ok"
