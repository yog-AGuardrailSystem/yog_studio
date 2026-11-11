"""PydanticAI: tools are functions registered with @agent.tool / @agent.tool_plain."""
from pydantic_ai import Agent, RunContext

agent = Agent("openai:gpt-4o", system_prompt="You manage customer orders.")


@agent.tool
def refund_order(ctx: RunContext[None], order_id: str, amount: int) -> str:
    """Refund part or all of an order."""
    return f"refunded {amount} on {order_id}"


@agent.tool_plain
def cancel_order(order_id: str) -> str:
    """Cancel an order that has not shipped."""
    return f"cancelled {order_id}"


@agent.tool_plain
def lookup_order(order_id: str) -> str:
    """Look up an order."""
    return "shipped"
