import uvicorn
from fastapi import APIRouter, FastAPI

from src.features.submissions.create_submission.router import (
    setup as setup_create_submission,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Submissions Service")

    api_router = APIRouter(prefix="/api/v1/submissions")
    setup_create_submission(api_router)
    app.include_router(api_router)

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    return app


app = create_app()


def start():
    uvicorn.run(app, host="0.0.0.0", port=8000)
