from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Hot Wheels visual backend activo"}

@app.post("/match")
async def match_hotwheel(image: UploadFile = File(...)):
    contents = await image.read()

    try:
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        width, height = img.size

        if width > height:
            top_match = {
                "name": "Volkswagen Beetle",
                "similarity": 0.81,
                "type": "Mainline",
                "rarity": "Media",
                "priceRange": "$100 - $220 MXN"
            }
        else:
            top_match = {
                "name": "Batmobile",
                "similarity": 0.78,
                "type": "Mainline",
                "rarity": "Media",
                "priceRange": "$100 - $260 MXN"
            }

        return {
            "topMatch": top_match,
            "matches": [top_match],
            "message": f"Imagen recibida correctamente: {width}x{height}"
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
