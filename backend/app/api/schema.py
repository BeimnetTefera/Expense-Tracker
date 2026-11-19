from typing import Literal

from pydantic import BaseModel, Field

# Shared rule for session ids: they come from the browser, so never trust them.
SESSION_ID = Field(min_length=8, max_length=150, pattern=r"^[A-Za-z0-9-]+$")


class ChatRequest(BaseModel):
    session_id: str = SESSION_ID
    message: str = Field(min_length=1, max_length=500)


# What the approval card in the UI needs to show.
class PendingApproval(BaseModel):
    approval_id: int
    expires_at: str
    expenses: list[dict]  # the exact expenses that would be deleted


# "How many messages can I still send?" - counted by the server, shown in the UI pill.
class ChatAllowance(BaseModel):
    limit: int                      # per-session messages per minute
    remaining: int
    resets_in: float | None = None  # seconds until one more message frees up


class ChatResponse(BaseModel):
    reply: str
    trace: list[dict]
    pending_approval: PendingApproval | None = None  # set -> UI shows the card
    allowance: ChatAllowance                          # fresh count AFTER this message


class ApprovalRequest(BaseModel):
    session_id: str = SESSION_ID
    decision: Literal["approve", "cancel"]  # anything else -> 422


class ApprovalResponse(BaseModel):
    approval_id: int
    status: str                     # EXECUTED or CANCELLED
    deleted_count: int | None = None


class ResetRequest(BaseModel):
    session_id: str = SESSION_ID


class ResetResponse(BaseModel):
    seeded: int  # how many sample expenses were added
