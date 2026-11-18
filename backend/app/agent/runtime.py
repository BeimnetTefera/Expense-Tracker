# Orchestrator: user -> LLM -> tools -> LLM ... until a final answer.

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from app.config import LOG_DIR
from app.agent.llm import get_llm_response, InvalidToolCallError
from app.agent.dispatcher import dispatch_tool
from app.services.expense_services import (
    cancel_delete,
    confirm_delete,
    get_pending_approval,
)


# Turn Pydantic results into real JSON for the LLM.
def to_json(value):
    # Pydantic models -> real JSON dicts (dates become "2026-11-17").
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    # Anything else json can't handle -> plain text, like before.
    return str(value)


# What run_agent gives back: the reply text + a record of every step it took.
class AgentResult(BaseModel):
    reply: str
    trace: list[dict]
    llm_unavailable: bool = False  # True -> the API answers 503 and doesn't charge the rate limit


# How long since `start` (a time.perf_counter() value), in whole milliseconds.
def elapsed_ms(start):
    return round((time.perf_counter() - start) * 1000)


MAX_STEPS = 5  # safety brake: max LLM rounds per message

# The LLM's job description; always the first message.
SYSTEM_MESSAGE = {
    "role": "system",
    "content": """
    You are a helpful expense tracking assistant. 
    Use the available tools when needed.
    Never claim an expense was saved unless the tool confirms it.
    Never calculate totals or counts yourself. 
    Always call get_summary or list_expenses to get them.

    """
}

# Work log of every step -> logs/agent.log
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "agent.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

logger = logging.getLogger(__name__)


# Keep the context small. Every message we keep is re-sent to the LLM on EVERY
# call, so an untrimmed history grows until one request blows the provider's
# tokens-per-minute budget. We keep the system prompt + the last few exchanges.
MAX_HISTORY_TURNS = 6


def trim_history(messages, max_turns=MAX_HISTORY_TURNS):
    # Cut only right before a USER message: a "tool" message must never be
    # separated from the assistant message whose tool_calls asked for it
    # (the API rejects orphan tool results).
    user_positions = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_positions) <= max_turns:
        return messages
    cut = user_positions[-max_turns]
    return [messages[0]] + messages[cut:]


# Read this session's past conversation (or start fresh with the system message).
def load_history(conn, owner):
    row = conn.execute(
        "SELECT messages FROM conversations WHERE owner_id = ?",
        (owner,),
    ).fetchone()

    # New session: nothing saved yet.
    if row is None:
        return [SYSTEM_MESSAGE.copy()]

    try:
        messages = json.loads(row["messages"])

        if (
            not isinstance(messages, list)
            or not messages
            or messages[0].get("role") != "system"
        ):
            raise ValueError("Invalid conversation history format.")

        # Always use the CURRENT system prompt, so prompt changes apply
        # to old sessions too (no need to delete history after an edit).
        messages[0] = SYSTEM_MESSAGE.copy()
        return trim_history(messages)

    except (json.JSONDecodeError, AttributeError, ValueError):
        raise RuntimeError("Conversation history could not be loaded.")


# Write this session's conversation back to the database (insert or replace).
def save_history(conn, owner, messages):
    conn.execute(
        """
        INSERT INTO conversations (owner_id, messages, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(owner_id) DO UPDATE SET
            messages = excluded.messages,
            updated_at = excluded.updated_at
        """,
        (
            owner,
            json.dumps(messages, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


# Convert the LLM reply into a plain dict we can store in history.
def serializaion_assistant_message(response):
    
    message = {
        "role": "assistant",
        "content": response.content,
    }
    
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                        
                },
            }
            
            for tool_call in response.tool_calls
        ]
    return message


# Handle one user message end to end; return the reply + trace.
def run_agent(user_message, registry, conn, owner="local"):
    trace = []  # one dict per step (LLM call or tool call), sent to the UI

    trace_id = str(uuid4())  # one id per request, to follow it in the log
    logger.info(
        "[trace_id=%s] Agent received a new request. ",
        trace_id,
    )
    
    # A) Pending delete? Only the user's yes/no decides (the LLM is not asked).
    pending = get_pending_approval(conn, owner)
    
    if pending is not None:
        user_reply = user_message.strip().lower()
        
        if user_reply == "yes":
            tool_name = "confirm_delete"
        elif user_reply == "no":
            tool_name = "cancel_delete"
            
        else:
            logger.info(
                "[trace_id=%s] Waiting for deletion approval (approval_id=%s).",
                trace_id,
                pending["id"],
            )
            return AgentResult(
                reply=(
                    "You have a pending deletion approval. "
                    "Please reply 'yes' to confirm or 'no' to cancel."
                ),
                trace=trace,
            )
    
    
        # Trusted path: call the SERVICE directly, not through the LLM's registry.
        # (confirm/cancel are deliberately not in the registry, so the LLM can't.)
        logger.info(
                    "[trace_id=%s] Executing trusted action: %s (approval_id=%s)",
                    trace_id,
                    tool_name,
                    pending["id"],
                )
        start = time.perf_counter()
        error_message = None
        try:
            if tool_name == "confirm_delete":
                confirm_delete(conn, owner, pending["id"])
                reply = "Deletion approved and executed successfully."
            else:
                cancel_delete(conn, owner, pending["id"])
                reply = "Deletion cancelled successfully."
        except (LookupError, ValueError) as error:
            error_message = str(error)
            reply = error_message

        # This path runs WITHOUT the LLM (step 0 = before any LLM call).
        trace.append({
            "step": 0,
            "kind": "approval",
            "tool": tool_name,
            "args": json.dumps({"approval_id": pending["id"]}),
            "ok": error_message is None,
            "ms": elapsed_ms(start),
            "error": error_message,
        })
        return AgentResult(reply=reply, trace=trace)
    
    # B) Load memory and add the new user message.
    try:
        messages = load_history(conn, owner)
        logger.info(
                "[trace_id=%s] Conversation history loaded.",
                trace_id,
            )
    except RuntimeError as error:
        logger.error(
            "[trace_id=%s] Conversation history could not be loaded.",
            trace_id,
        )
        return AgentResult(reply=str(error), trace=trace)

    messages.append(
        {
            "role": "user",
            "content": user_message,
        })

    # C) Loop: ask LLM -> run requested tools -> send results back -> repeat.
    for step in range(MAX_STEPS):
        # 1. Ask the LLM what to do
        start = time.perf_counter()
        try:
            response = get_llm_response(messages)
            logger.info(
                        "[trace_id=%s] LLM response received (step %s).",
                        trace_id,
                        step + 1,
                    )
        except InvalidToolCallError as error:
            # The model broke a tool's schema. Tell it what went wrong and loop
            # again - it usually fixes the arguments. MAX_STEPS still caps retries.
            logger.warning(
                "[trace_id=%s] Invalid tool call rejected by Groq: %s",
                trace_id,
                error,
            )
            trace.append({
                "step": step + 1,
                "kind": "llm",
                "ok": False,
                "ms": elapsed_ms(start),
                "error": "INVALID_TOOL_CALL",
            })
            messages.append({
                "role": "system",
                "content": (
                    "Your last tool call was rejected because its arguments did not "
                    f"match the tool schema: {error}. Fix the arguments and try again."
                ),
            })
            continue

        except Exception:
            logger.exception(
                        "[trace_id=%s] LLM request failed.",
                        trace_id,
                    )
            trace.append({
                "step": step + 1,
                "kind": "llm",
                "ok": False,
                "ms": elapsed_ms(start),
                "error": "LLM_UNAVAILABLE",
            })
            return AgentResult(
                reply="The AI service is currently unavailable. Please try again later.",
                llm_unavailable=True,
                trace=trace,
            )

        # Record the LLM step: how long it took and how many tools it asked for.
        trace.append({
            "step": step + 1,
            "kind": "llm",
            "ok": True,
            "ms": elapsed_ms(start),
            "tool_calls": len(response.tool_calls or []),
        })

        # 2. Add the LLM response to conversation history
        assistant_message = serializaion_assistant_message(response)
        messages.append(assistant_message)

        # 3. No tool call: final answer -> save and return it.
        if not response.tool_calls:
            logger.info(
                        "[trace_id=%s] Agent completed the request.",
                        trace_id,
                    )
            save_history(conn, owner, messages)
            return AgentResult(reply=response.content or "", trace=trace)

        # 4. Run each requested tool (validated by the dispatcher).
        for tool_call in response.tool_calls:
            tool_name = tool_call.function.name
            arguments = tool_call.function.arguments

            logger.info(
                "[trace_id=%s] Executing tool: %s",
                trace_id,
                tool_name,
            )
            start = time.perf_counter()
            result = dispatch_tool(
                tool_name,
                arguments,
                registry,
            )
            logger.info(
                "[trace_id=%s] Tool execution finished: %s | success=%s",
                trace_id,
                tool_name,
                result["ok"],
            )
            # Record the tool step: what was called, with what, and did it work.
            trace.append({
                "step": step + 1,
                "kind": "tool",
                "tool": tool_name,
                "args": arguments,
                "ok": result["ok"],
                "ms": elapsed_ms(start),
                "error": None if result["ok"] else result["error"]["message"],
            })
            if not result["ok"]:
                logger.warning(
                    "[trace_id=%s] Tool %s failed: %s",
                    trace_id,
                    tool_name,
                    result["error"]["message"],
                )

            # 5. Send the result (even errors) back to the LLM.
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=to_json),
            })

    # Hit MAX_STEPS without a final answer: stop.
    logger.warning(
        "[trace_id=%s] Max steps (%s) reached without a final answer.",
        trace_id,
        MAX_STEPS,
    )
    save_history(conn, owner, messages)

    return AgentResult(
        reply="I reached the maximum number of steps. Please try again.",
        trace=trace,
    )
