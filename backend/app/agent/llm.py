# Handles communication with Groq

import time

from groq import Groq

from app.agent.definitions import TOOLS
from app.config import GROQ_API_KEY



MODEL = "openai/gpt-oss-120b"

client = Groq(
    api_key=GROQ_API_KEY,
    timeout=30.0,
    max_retries=0,
)

# The model asked for a tool with arguments that break the schema.
# Groq rejects this itself (400 "tool_use_failed"). Not an outage: the model
# can fix it if we show it the error - so the runtime handles this separately.
class InvalidToolCallError(Exception):
    pass


# How long to wait before retrying. Groq's 429 says exactly when it's safe
# ("retry-after" header) - use that instead of guessing, capped so a visitor
# never waits forever.
MAX_WAIT_SECONDS = 8


def retry_wait(error, attempt):
    response = getattr(error, "response", None)
    retry_after = response.headers.get("retry-after") if response is not None else None
    try:
        wait = float(retry_after) if retry_after else 2 ** attempt
    except ValueError:
        wait = 2 ** attempt
    return min(max(wait, 0.5), MAX_WAIT_SECONDS)


def get_llm_response(messages):

    max_retries = 3

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            return response.choices[0].message

        except Exception as error:
            status_code = getattr(error, "status_code", None)

            # Bad tool arguments: don't retry blindly, let the model correct itself.
            if status_code == 400 and "tool_use_failed" in str(error):
                raise InvalidToolCallError(str(error)) from error

            retryable = (
                status_code in (408, 409, 429)
                or (status_code is not None and status_code >= 500)
                or status_code is None
            )
            
            if not retryable or attempt == max_retries:
                raise RuntimeError("LLM_UNAVAILABLE") from error
            
            time.sleep(retry_wait(error, attempt))