import multiprocessing

import uvicorn
from fastapi import APIRouter, FastAPI

from src.features.submissions.create_submission.router import (
    setup as setup_create_submission,
)
from src.workers.outbox_relay import main as outbox_relay


def create_app() -> FastAPI:
    """Cria e configura a aplicacao FastAPI."""
    app = FastAPI(title="Submissions Service")

    # Configura roteador de API v1
    api_router = APIRouter(prefix="/api/v1/submissions")
    setup_create_submission(api_router)

    app.include_router(api_router)

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    return app


# Instancia global para o uvicorn (caso rode via CLI)
app = create_app()


def start_api():
    """Inicia o servidor FastAPI."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


def start():
    """Ponto de entrada para subir o backend e os daemons."""
    print("--- Iniciando Submissions Service (API + Daemons) ---")

    # Inicia o Outbox Relay como um processo separado (daemon)
    print("--- Iniciando Outbox Relay Daemon ---")
    relay_process = multiprocessing.Process(target=outbox_relay, name="OutboxRelay")
    relay_process.daemon = True
    relay_process.start()

    # Inicia a API (processo principal)
    print("--- Iniciando API na porta 8000 ---")
    try:
        start_api()
    except KeyboardInterrupt:
        print("\nEncerrando servicos...")
    finally:
        if relay_process.is_alive():
            relay_process.terminate()
            relay_process.join()


if __name__ == "__main__":
    start()
