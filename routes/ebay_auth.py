from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from services.ebay_token_service import exchange_code_for_token
from config import (
    EBAY_APP_CLIENT_ID,
    EBAY_RUNAME,
    EBAY_ENV,
    EBAY_SCOPES,
)

router = APIRouter(prefix="/ebay", tags=["eBay Auth"])


@router.get("/start")
def ebay_start():
    if not EBAY_APP_CLIENT_ID or not EBAY_RUNAME:
        return JSONResponse(
            status_code=500,
            content={"error": "Faltan EBAY_APP_CLIENT_ID o EBAY_RUNAME en variables de entorno"}
        )

    base_url = (
        "https://auth.sandbox.ebay.com/oauth2/authorize"
        if EBAY_ENV.lower() == "sandbox"
        else "https://auth.ebay.com/oauth2/authorize"
    )

    params = (
        f"client_id={EBAY_APP_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={EBAY_RUNAME}"
        f"&scope={EBAY_SCOPES}"
    )

    return RedirectResponse(url=f"{base_url}?{params}")


@router.get("/callback")
def ebay_callback(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            f"""
            <html>
                <body style="font-family: Arial; padding: 30px;">
                    <h2>Autorización rechazada</h2>
                    <p>Error: {error}</p>
                </body>
            </html>
            """
        )

    if not code:
        return HTMLResponse(
            """
            <html>
                <body style="font-family: Arial; padding: 30px;">
                    <h2>No llegó el code de eBay</h2>
                    <p>Revisa la configuración del redirect URL.</p>
                </body>
            </html>
            """,
            status_code=400
        )

    token_result = exchange_code_for_token(code)

    if not token_result.get("success"):
        return HTMLResponse(
            f"""
            <html>
                <body style="font-family: Arial; padding: 30px;">
                    <h2>Error obteniendo token</h2>
                    <pre>{token_result.get("message", "Error desconocido")}</pre>
                </body>
            </html>
            """,
            status_code=500
        )

    return HTMLResponse(
        """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h2>Autorización completada</h2>
                <p>Ya se obtuvo el token de eBay correctamente.</p>
                <p>Puedes cerrar esta ventana.</p>
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
                <p>La autorización fue aceptada correctamente.</p>
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
                <p>El usuario rechazó la autorización.</p>
            </body>
        </html>
        """
    )
