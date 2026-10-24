"""Finance MCP server using the module-import style (`import ... as fm`) and `server.tool`."""
import smtplib

import mcp.server.fastmcp as fm

server = fm.FastMCP("finance")


@server.tool()
def transfer_funds(from_account: str, to_account: str, amount: float, currency: str = "USD") -> dict:
    """Transfer money between two accounts."""
    return {"from": from_account, "to": to_account, "amount": amount, "currency": currency}


@server.tool()
def get_balance(account_id: str) -> float:
    """Read the current balance of an account."""
    return 0.0


@server.tool()
def send_receipt_email(to: str, body: str) -> str:
    """Email a receipt to a customer."""
    with smtplib.SMTP("localhost") as s:
        s.sendmail("bank@example.com", to, body)
    return "sent"
