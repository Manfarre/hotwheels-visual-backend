from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.ebay_search_service import search_ebay_items
from services.ebay_token_service import get_application_token
from config import EBAY_ENV

router = APIRouter(prefix="/api/ebay", tags=["eBay Tools"])


def _safe_token_status(token_result: dict) -> dict:
    """
    Devuelve solo metadatos seguros del token.
    Nunca expone access_token ni raw payload al cliente.
    """
    return {
        "success": True,
        "env": EBAY_ENV,
        "token_type": token_result.get("token_type", ""),
        "expires_in": token_result.get("expires_in", 0),
        "message": "Token de aplicación obtenido correctamente.",
    }


@router.get("/token")
def ebay_token():
    """
    Endpoint de diagnóstico seguro.
    Valida que eBay entregue token, pero no lo expone al cliente.
    """
    token_result = get_application_token()

    if not token_result.get("success"):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "env": EBAY_ENV,
                "message": token_result.get("message", "No se pudo obtener token"),
            },
        )

    return _safe_token_status(token_result)


@router.get("/search")
def ebay_search(
    q: str = Query(..., description="Texto a buscar en eBay"),
    limit: int = Query(10, ge=1, le=20)
):
    return search_ebay_items(query=q, limit=limit)
