// One plain-English line per trace step, so anyone who opens it learns WHY it's built this way.
const TOOL_WHY = {
  save_expense: "Arguments checked by Pydantic, then saved to SQLite.",
  list_expenses: "Read straight from SQLite.",
  search_expenses: "Filtered in SQL with safe ? placeholders.",
  get_summary: "Totals come from SQL (SUM / GROUP BY), never from the model doing maths.",
  prepare_delete: "Only proposes the delete. Nothing is removed until you approve.",
};

export function explain(s) {
  if (s.kind === "approval") return "Your click called the service directly. The LLM has no tool for this.";
  if (s.kind === "llm") {
    if (s.ok === false)
      return s.error === "INVALID_TOOL_CALL"
        ? "Sent arguments that broke the tool's schema. It was shown the error and tried again."
        : "The model couldn't be reached.";
    return s.tool_calls
      ? `Read your message and the tool list, then asked for ${s.tool_calls} tool${s.tool_calls > 1 ? "s" : ""}. It can only ask; Python decides what runs.`
      : "Turned the results into the reply below.";
  }
  if (s.ok === false) return "Rejected. The error went back to the LLM so it could correct itself.";
  return TOOL_WHY[s.tool] || "Validated by Pydantic, then run.";
}

export const EXAMPLES = [
  "How much have I spent this week?",
  "I spent 85 birr on coffee today",
  "What's my biggest category this month?",
  "Show my food expenses",
  "Delete my cinema ticket",
];
