"""Plain function-calling agent: tools are declared in an OpenAI-style `tools=[...]` schema."""
import os
import shutil

from openai import OpenAI

client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delete_user_data",
            "description": "Delete all stored data for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "hard_delete": {"type": "boolean"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "subject", "body"],
            },
        },
    },
]


def delete_user_data(user_id: str, hard_delete: bool = False) -> str:
    shutil.rmtree(f"/data/{user_id}")
    return "deleted"


def send_email(to: str, subject: str, body: str) -> str:
    return "sent"


def run(messages):
    return client.chat.completions.create(model="gpt-4o", messages=messages, tools=TOOLS)
