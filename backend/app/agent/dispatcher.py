# input data validation logic


import json
from pydantic import ValidationError
import sqlite3

from app.models import (
    ExpenseCreate,
    ListExpensesArgs,
    SummaryQuery,
    SearchFilters,
    PrepareDeleteArgs,
)

ARGUMENT_MODELS = {
    "save_expense": ExpenseCreate,
    "list_expenses": ListExpensesArgs,
    "get_summary": SummaryQuery,
    "search_expenses": SearchFilters,
    "prepare_delete": PrepareDeleteArgs,
}

def dispatch_tool(tool_name, arguments, registry):
    
    # Find the actual function
    function = registry.get(tool_name)

    if function is None:
        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": f"Unknown tool: {tool_name}"
            }
        }
        
    # Find the Pydantic model
    model = ARGUMENT_MODELS.get(tool_name)

    if model is None:
        return {
            "ok": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": f"No argument model configured for: {tool_name}"
            }
        }
        
    try:
        # Parse JSON and validate arguments
        raw_arguments = json.loads(arguments)
        validated_arguments = model.model_validate(raw_arguments)

        # Execute the actual function
        result = function(validated_arguments)

        return {
            "ok": True,
            "result": result,
        }

    except LookupError as error:
        return {
            "ok": False,
            "error": {
                "code": "NOT_FOUND",
                "message": str(error),
            },
        }
        
    except sqlite3.Error as error:
        return {
            "ok": False,
            "error": {
                "code": "DB_ERROR",
                "message": "A database operation failed.",
            },
        }  
          
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        return {
            "ok": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(error),
            },
        }