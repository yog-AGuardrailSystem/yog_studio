"""OpenAI Agents SDK: tools are functions marked with @function_tool."""
from agents import Agent, function_tool


@function_tool
def transfer_money(from_account: str, to_account: str, amount: int) -> str:
    """Move money between two accounts."""
    return f"moved {amount} from {from_account} to {to_account}"


@function_tool(name_override="close_account")
def close_account_impl(account: str) -> str:
    """Permanently close an account."""
    return f"closed {account}"


@function_tool
def get_balance(account: str) -> str:
    """Read an account balance."""
    return "100"


agent = Agent(name="Banker", instructions="Help with accounts.", tools=[transfer_money, close_account_impl, get_balance])
