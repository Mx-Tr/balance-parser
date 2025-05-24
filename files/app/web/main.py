from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from app.db import Session, Balance
from datetime import timedelta

app = FastAPI()
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/")
def index(request: Request):
    rows = Session().query(Balance).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "rows": rows, "timedelta": timedelta}
    )