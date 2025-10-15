"""
Plan-related API routes.

This module handles all plan endpoints including:
- Getting current plan and history
- Listing all plan versions
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.plan import read_plan_from_database, read_plan_history_from_database, plan_to_dict


async def get_plans(request: Request) -> JSONResponse:
    """
    Return all plans associated with a chat ordered by most recent first.
    
    Query parameters:
    - chat_id: The chat identifier (required)
    - limit: Optional maximum number of plans to return
    
    Returns:
        JSONResponse with list of serialized plans.
    """
    try:
        chat_id = request.query_params.get("chat_id")
        if not chat_id:
            return JSONResponse({"error": "chat_id parameter is required"}, status_code=400)

        limit_param = request.query_params.get("limit")
        limit = int(limit_param) if limit_param is not None else None

        plans = read_plan_history_from_database(chat_id, limit=limit)
        serialised_plans = [plan_to_dict(plan) for plan in plans if plan]
        return JSONResponse(serialised_plans)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_plan(request: Request) -> JSONResponse:
    """
    Return the current plan and historical versions for a chat.
    
    Query parameters:
    - chat_id: The chat identifier (required)
    
    Returns:
        JSONResponse with 'current' and 'history' keys containing plan data.
    """
    try:
        chat_id = request.query_params.get("chat_id")
        if not chat_id:
            return JSONResponse({"error": "chat_id parameter is required"}, status_code=400)

        current_plan = plan_to_dict(read_plan_from_database(chat_id))
        history_plans = [plan_to_dict(p) for p in read_plan_history_from_database(chat_id)]

        # Exclude the current plan from history list if duplicated
        if current_plan:
            current_id = current_plan.get("id")
            current_key = current_plan.get("versionKey")
            pruned = []
            for p in history_plans:
                if not p:
                    continue
                if current_id is not None and p.get("id") == current_id:
                    continue
                if current_key and p.get("versionKey") == current_key:
                    continue
                pruned.append(p)
            history_plans = pruned
        else:
            history_plans = [p for p in history_plans if p]

        return JSONResponse({
            "current": current_plan,
            "history": history_plans,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
