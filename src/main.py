import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from src.features.submissions.create_submission.router import setup as setup_create

app = FastAPI(title="Submissions Service", version="1.0.0")

router = APIRouter(prefix="/api/v1/submissions")

setup_create(router)

# get_submission e list_submissions serao adicionados nas proximas features

app.include_router(router)


def start():
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
