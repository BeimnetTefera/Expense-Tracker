# HTTP boundary: translates web requests into run_agent() / service calls.
# It decides NOTHING about tools - same agent as the CLI, different "door".

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS, DB_PATH
from app.db import get_connection, init_db
from app.agent.registry import build_registry
from app.agent.runtime import run_agent
from app.services.expense_services import (
    cancel_delete,
    confirm_delete,
    get_expenses_by_ids,
    get_pending_approval,
    list_expenses,
)
from app.seed import reset_demo
from app.api.limits import (
    chat_allowance,
    check_chat_limits,
    close_persistence,
    load_persisted_hits,
    refund_chat_limits,
)
from app.api.schema import (
    ApprovalRequest,
    ApprovalResponse,
    ChatAllowance,
    ChatRequest,
    ChatResponse,
    PendingApproval,
    ResetRequest,
    ResetResponse,
)


# Runs ONCE when the server starts (before any request): make sure tables exist.
@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
    finally:
        conn.close()
    # Reload message counts from before a restart (else everyone gets a fresh 10/10).
    load_persisted_hits(DB_PATH)
    yield  # the server runs while we're "inside" here
    close_persistence()


app = FastAPI(title="Expense Tracker Agent API", lifespan=lifespan)

# CORS: browsers only let pages from THESE sites call the API. Never "*" in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# For the host's "is it alive?" checks. Touches nothing (no DB, no Groq),
# so it stays fast and green even if Groq is having a bad day.
@app.get("/health")
def health_check():
    return {"status": "ok"}


def client_ip_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# The UI's "N/10 msgs left" pill. Read-only: looking doesn't use up a message.
@app.get("/limits", response_model=ChatAllowance)
def get_limits(request: Request, session_id: str = Query(min_length=8, max_length=150, pattern=r"^[A-Za-z0-9-]+$")):
    return chat_allowance(session_id, client_ip_of(request))


# Ask the DATABASE (source of truth) if a delete is waiting - never parse LLM text.
def load_pending_approval(conn, owner):
    row = get_pending_approval(conn, owner)
    if row is None:
        return None

    expenses = get_expenses_by_ids(conn, owner, json.loads(row["expense_ids"]))
    return PendingApproval(
        approval_id=row["id"],
        expires_at=row["expires_at"],
        expenses=[e.model_dump(mode="json") for e in expenses],
    )


# Plain `def` (not async): run_agent blocks on Groq + SQLite, so FastAPI runs it
# in a worker thread and other visitors aren't frozen while we wait.
@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request):
    # Rate limit BEFORE any work: a refused request costs no Groq tokens.
    client_ip = client_ip_of(request)
    wait = check_chat_limits(body.session_id, client_ip)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please wait a moment and try again.",
            headers={"Retry-After": str(int(wait) + 1)},  # seconds, standard header
        )

    # One connection per request: SQLite connections can't be shared across threads.
    conn = get_connection(DB_PATH)
    try:
        # The session id becomes the owner -> every query is scoped to this visitor.
        registry = build_registry(conn, owner=body.session_id)
        result = run_agent(body.message, registry, conn, owner=body.session_id)

        # Groq was down / out of quota: the visitor got no answer, so refund the
        # rate-limit slot and say so with 503 (the browser won't count it either).
        if result.llm_unavailable:
            refund_chat_limits(body.session_id, client_ip)
            raise HTTPException(
                status_code=503,
                detail="The AI is busy right now (free-tier limit). Please try again in a few seconds.",
                headers={"Retry-After": "5"},
            )

        return ChatResponse(
            reply=result.reply,
            trace=result.trace,
            pending_approval=load_pending_approval(conn, body.session_id),
            allowance=chat_allowance(body.session_id, client_ip),
        )
    finally:
        conn.close()  # always runs, even if run_agent raised an error


# The human's button click. NO LLM here: a trusted path straight to the service.
@app.post("/approvals/{approval_id}", response_model=ApprovalResponse)
def decide_approval(approval_id: int, body: ApprovalRequest):
    conn = get_connection(DB_PATH)
    try:
        if body.decision == "approve":
            result = confirm_delete(conn, body.session_id, approval_id)
        else:
            result = cancel_delete(conn, body.session_id, approval_id)
        return ApprovalResponse(**result)

    except LookupError:
        # Unknown id OR another session's id: same answer, so we leak nothing.
        raise HTTPException(status_code=404, detail="Approval not found.")
    except ValueError as error:
        # Exists, but already used / cancelled / expired.
        raise HTTPException(status_code=409, detail=str(error))
    finally:
        conn.close()


# The UI's expense table: read straight from the service. No LLM = fast, free, exact.
@app.get("/expenses")
def get_expenses(session_id: str = Query(min_length=8, max_length=150, pattern=r"^[A-Za-z0-9-]+$")):
    conn = get_connection(DB_PATH)
    try:
        expenses = list_expenses(conn, session_id, limit=100)
        return [e.model_dump(mode="json") for e in expenses]
    finally:
        conn.close()


# "Reset demo" button (and first visit): wipe this session, add sample data.
@app.post("/demo/reset", response_model=ResetResponse)
def demo_reset(body: ResetRequest):
    conn = get_connection(DB_PATH)
    try:
        return ResetResponse(seeded=reset_demo(conn, body.session_id))
    finally:
        conn.close()
