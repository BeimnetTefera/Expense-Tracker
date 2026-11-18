import os
from groq import Groq
from dotenv import load_dotenv
from app.models import ExpenseCreate, Expense
import json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

schema = ExpenseCreate.model_json_schema()
tools = [
    {
        "type": "function",
        "function": {
            "name": "save_expense",
            "description": "Save a user's expense.",
            "parameters": schema
        }
    }
]


response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "user", "content": "I spent 300 ETB on lunch."}
    ],
    tools=tools,
    tool_choice="auto"
)

message = response.choices[0].message

print("Role:", message.role)
print("Content:", message.content)
print("Tool calls:", message.tool_calls)
print("Finish reason:", response.choices[0].finish_reason)


