from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy():
    return """
    <html>
      <head>
        <title>Privacy Policy</title>
      </head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h1>Privacy Policy</h1>
        <p>
          Business Technology Hot Wheels Scanner does not persist personal
          eBay user data.
        </p>
        <p>
          This application is used to analyze collectible toy listings and
          public item information for identification and price reference.
        </p>
      </body>
    </html>
    """


@router.get("/ebay/auth/accepted", response_class=HTMLResponse)
def ebay_auth_accepted():
    return """
    <html>
      <head>
        <title>Authorization completed</title>
      </head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h1>Authorization completed</h1>
        <p>You can close this window and return to the app.</p>
      </body>
    </html>
    """


@router.get("/ebay/auth/declined", response_class=HTMLResponse)
def ebay_auth_declined():
    return """
    <html>
      <head>
        <title>Authorization cancelled</title>
      </head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h1>Authorization cancelled</h1>
        <p>No permissions were granted.</p>
      </body>
    </html>
    """
