from fastapi import APIRouter
from core.registry import list_platforms

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("")
def get_platforms():
    platforms = list_platforms()
    return [p for p in platforms if p["name"] not in ("cursor", "tavily")]
