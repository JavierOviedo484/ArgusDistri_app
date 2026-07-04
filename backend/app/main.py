"""
FastAPI main — punto de entrada del servidor.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os
import sys

# Asegurar que backend/ está en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import init_db
from app.api.v1 import router as api_router

app = FastAPI(title="Distribuidor de Documentos", version="1.0.0")

# Directorios
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Static files
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API routes
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
