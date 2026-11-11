"""LangChain agent: tools are plain functions marked with @tool."""
import os
import shutil

from langchain_core.tools import tool


@tool
def delete_file(path: str) -> str:
    """Delete a file from the workspace."""
    os.remove(path)
    return f"deleted {path}"


@tool("send_report")
def send_report(recipient: str, subject: str, body: str) -> str:
    """Email a report to one recipient."""
    return f"sent '{subject}' to {recipient}"


@tool
def archive_folder(folder: str, destination: str = "archive") -> str:
    """Move a whole folder into the archive."""
    shutil.move(folder, destination)
    return "archived"


def build_agent(llm):
    return llm.bind_tools([delete_file, send_report, archive_folder])
