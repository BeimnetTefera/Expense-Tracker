
from app.config import DB_PATH
from app.db import get_connection, init_db
from app.agent.registry import build_registry
from app.agent.runtime import run_agent


def main():
    # 1. Connect to the database
    conn = get_connection(DB_PATH)
    init_db(conn)

    # 2. Build the tool registry
    registry = build_registry(conn)

    print("Expense Tracker Agent is ready!")
    print("Type 'exit' to quit.\n")

    # 3. Start the conversation loop
    while True:
        user_message = input("You: ").strip()

        if user_message.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if not user_message:
            continue

        # 4. Run the agent
        response = run_agent(user_message, registry, conn, owner='local')

        # 5. Show what the agent did (the trace), then its reply
        for s in response.trace:
            if s["kind"] == "llm":
                print(f"  [step {s['step']}] llm  {s['ms']} ms  tool_calls={s.get('tool_calls', '-')}")
            else:
                status = "ok" if s["ok"] else f"FAILED: {s['error']}"
                print(f"  [step {s['step']}] tool {s['tool']} {s['args']}  {s['ms']} ms  {status}")

        print(f"\nAgent: {response.reply}\n")

    conn.close()


if __name__ == "__main__":
    main()
