from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.ebay_search_service import search_ebay_items
from services.ebay_token_service import get_application_token

router = APIRouter(prefix="/api/ebay", tags=["eBay Tools"])


@router.get("/token")
def ebay_token():
    token_result = get_application_token()

    if not token_result.get("success"):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": token_result.get("message", "No se pudo validar eBay."),
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Token validado internamente. Ya no se expone en la respuesta.",
            "expires_in": token_result.get("expires_in", 0),
            "token_type": token_result.get("token_type", ""),
        },
    )


@router.get("/search")
def ebay_search(
    q: str = Query(..., description="Texto a buscar en eBay"),
    limit: int = Query(10, ge=1, le=20)
):
    return search_ebay_items(query=q, limit=limit)
