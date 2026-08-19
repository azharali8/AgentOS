from fastapi import APIRouter
from backend.app.tools.registry import ToolRegistry

router = APIRouter()

@router.get("/tools")
def list_tools():
    return {"tools": [t.dict() for t in ToolRegistry.list_tools()]}
