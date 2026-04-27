from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from services.ebay_token_service import get_application_token
from config import EBAY_CLIENT_ID, EBAY_ENV

router = APIRouter(prefix="/ebay", tags=["eBay Auth"])


@router.get("/start")
def ebay_start():
    """
    Obtiene un token de aplicación de eBay.
    Sirve para validar que las credenciales cargadas en Render funcionan.
    """
    token_result = get_application_token()

    if not token_result.get("success"):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "env": EBAY_ENV,
                "client_id_loaded": bool(EBAY_CLIENT_ID),
                "message": token_result.get("message", "No se pudo obtener token"),
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "env": EBAY_ENV,
            "client_id_loaded": bool(EBAY_CLIENT_ID),
            "token_type": token_result.get("token_type", ""),
            "expires_in": token_result.get("expires_in", 0),
            "access_token": token_result.get("access_token", ""),
        },
    )


@router.get("/status")
def ebay_status():
    """
    Ruta simple para validar si el módulo de eBay está activo
    y si Render está leyendo variables.
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "module": "ebay_auth",
            "env": EBAY_ENV,
            "client_id_loaded": bool(EBAY_CLIENT_ID),
        },
    )


@router.get("/callback")
def ebay_callback():
    return HTMLResponse(
        """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h2>Callback temporal</h2>
                <p>La ruta de callback está activa correctamente.</p>
                <p>El flujo OAuth completo lo implementamos después.</p>
            </body>
        </html>
        """
    )


@router.get("/accepted")
def ebay_accepted():
    return HTMLResponse(
        """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h2>Autorización aceptada</h2>
                <p>La ruta accepted está activa correctamente.</p>
            </body>
        </html>
        """
    )


@router.get("/declined")
def ebay_declined():
    return HTMLResponse(
        """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h2>Autorización rechazada</h2>
                <p>La ruta declined está activa correctamente.</p>
            </body>
        </html>
        """
    )
