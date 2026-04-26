from fastapi import APIRouter, Query

from services.ebay_search_service import search_ebay_items
from services.ebay_token_service import get_application_token

router = APIRouter(prefix="/api/ebay", tags=["eBay Tools"])


@router.get("/token")
def ebay_token():
    return get_application_token()


@router.get("/search")
def ebay_search(
    q: str = Query(..., description="Texto a buscar en eBay"),
    limit: int = Query(10, ge=1, le=20)
):
    return search_ebay_items(query=q, limit=limit)
