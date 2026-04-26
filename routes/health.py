from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {"message": "Hot Wheels backend activo"}


@router.get("/health")
def health():
    return {"status": "ok"}
