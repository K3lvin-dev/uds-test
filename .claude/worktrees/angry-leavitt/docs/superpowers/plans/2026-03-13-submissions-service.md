# Submissions Service Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar micro-servico REST para registrar e corrigir redacoes com FastAPI, Postgres, LocalStack (S3+SQS) e Gemini Flash.

**Architecture:** Vertical Slice Architecture (VSA) — codigo organizado por feature/use-case. Cada feature tem um entry point `setup()` que recebe o router. Platform layer contem infra compartilhada (DB, S3, SQS, config). Worker e um event consumer slice separado.

**Tech Stack:** Python 3.13, uv, FastAPI 0.135.x, SQLAlchemy 2.0.48 + asyncpg 0.31.0, boto3 1.42.x, google-genai (NAO google-generativeai), pydantic-settings 2.13.x, Docker Compose (Postgres 17-alpine + LocalStack 4.0).

**Git Strategy:** Trunk-Based Development. Uma branch de feature por chunk, merge para `main` apos cada feature completa.
- `feat/infra-setup`
- `feat/platform`
- `feat/create-submission`
- `feat/get-submission`
- `feat/list-submissions`
- `feat/worker`
- `feat/readme`

> **IMPORTANTE:** O assistente NAO faz commits nem git add. O engenheiro decide o que sobe.

---

## File Map

```
uds-test/
  docker-compose.yml              — Postgres 17 + LocalStack 4.0 com healthchecks
  schema.sql                      — DDL tabela submissions + indices
  pyproject.toml                  — dependencias (uv)
  .env.example                    — variaveis de ambiente documentadas
  .env                            — variaveis reais (nao commitar)
  scripts/
    init-aws.sh                   — cria bucket S3 e fila SQS no LocalStack
  src/
    __init__.py                   — vazio, torna src um pacote importavel
    main.py                       — composition root FastAPI
    worker.py                     — composition root Worker
    platform/
      __init__.py
      config.py                   — Settings via pydantic-settings (le .env)
      database.py                 — async engine + session factory + get_db dep
      models.py                   — SQLAlchemy model Submission (compartilhado)
      s3.py                       — wrapper boto3: upload_text / download_text
      sqs.py                      — wrapper boto3: publish / receive / delete
    features/
      __init__.py
      submissions/
        __init__.py
        create_submission/
          __init__.py
          schemas.py              — CreateSubmissionRequest / CreateSubmissionResponse
          handler.py              — logica: S3 upload + DB insert + SQS publish
          router.py               — setup(router) — entry point VSA
        get_submission/
          __init__.py
          schemas.py              — SubmissionDetailResponse
          handler.py              — DB query by id, 404 se nao achar
          router.py               — setup(router) — entry point VSA
        list_submissions/
          __init__.py
          schemas.py              — SubmissionSummary + ListSubmissionsResponse
          handler.py              — DB query by student_id + paginacao offset/limit
          router.py               — setup(router) — entry point VSA
    worker/
      __init__.py
      grade_submission/
        __init__.py
        schemas.py                — GradingResult + CriterionResult (Pydantic)
        grader.py                 — chamada Gemini Flash com structured output
        handler.py                — orquestra: DB fetch + idempotencia + S3 + grader + DB update
        consumer.py               — setup() — SQS poll loop (entry point VSA)
  README.md
```

---

## Chunk 1: Infra & Project Setup

**Branch:** `feat/infra-setup`

### Task 1: Estrutura de diretorios e arquivos vazios

- [x] Crie a estrutura de diretorios:

```bash
mkdir -p scripts
mkdir -p src/platform
mkdir -p src/features/submissions/create_submission
mkdir -p src/features/submissions/get_submission
mkdir -p src/features/submissions/list_submissions
mkdir -p src/worker/grade_submission
```

- [x] Crie todos os `__init__.py` vazios:

```bash
touch src/__init__.py
touch src/platform/__init__.py
touch src/features/__init__.py
touch src/features/submissions/__init__.py
touch src/features/submissions/create_submission/__init__.py
touch src/features/submissions/get_submission/__init__.py
touch src/features/submissions/list_submissions/__init__.py
touch src/worker/__init__.py
touch src/worker/grade_submission/__init__.py
```

---

### Task 2: pyproject.toml

- [x] Crie `pyproject.toml`:

```toml
[project]
name = "uds-test"
version = "0.1.0"
description = "Micro-service for grading essays"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.135.0",
    "uvicorn[standard]>=0.41.0",
    "sqlalchemy[asyncio]>=2.0.48",
    "asyncpg>=0.31.0",
    "boto3>=1.42.0",
    "google-genai",
    "pydantic-settings>=2.13.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

- [x] Instale as dependencias:

```bash
uv sync
```

Saida esperada: resolucao das dependencias e criacao do `.venv/`.

---

### Task 3: docker-compose.yml

- [x] Crie `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: submissions_postgres
    environment:
      POSTGRES_DB: submissions_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - ./schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d submissions_db"]
      interval: 5s
      timeout: 5s
      retries: 10

  localstack:
    image: localstack/localstack:4.0
    container_name: submissions_localstack
    ports:
      - "4566:4566"
    environment:
      SERVICES: s3,sqs
      AWS_DEFAULT_REGION: us-east-1
    volumes:
      - ./scripts/init-aws.sh:/etc/localstack/init/ready.d/init-aws.sh
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 5s
      retries: 10
```

---

### Task 4: schema.sql

- [x] Crie `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    score NUMERIC(4, 2),
    criteria JSONB,
    overall_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submissions_student_id
    ON submissions (student_id);

CREATE INDEX IF NOT EXISTS idx_submissions_student_id_created_at
    ON submissions (student_id, created_at DESC);
```

---

### Task 5: scripts/init-aws.sh

- [x] Crie `scripts/init-aws.sh`:

```bash
#!/bin/bash
set -e

echo "Initializing LocalStack resources..."

awslocal s3 mb s3://submissions-bucket

awslocal sqs create-queue \
  --queue-name submissions-queue \
  --attributes VisibilityTimeout=120

echo "LocalStack resources created successfully."
```

- [x] Torne executavel:

```bash
chmod +x scripts/init-aws.sh
```

---

### Task 6: .env.example e .env

- [x] Crie `.env.example`:

```dotenv
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/submissions_db

# AWS / LocalStack
AWS_ENDPOINT_URL=http://localhost:4566
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
S3_BUCKET=submissions-bucket
SQS_QUEUE_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/submissions-queue

# Gemini AI
GEMINI_API_KEY=your-gemini-api-key-here
```

- [x] Crie `.env` a partir do exemplo (e preencha a `GEMINI_API_KEY`):

```bash
cp .env.example .env
```

- [x] Verifique que `.env` esta no `.gitignore` (ja deve estar pelo template padrao).

---

### Task 7: Subir infra local e verificar

- [x] Suba os containers:

```bash
docker compose up -d
```

- [x] Aguarde healthchecks ficarem healthy:

```bash
docker compose ps
```

Saida esperada: `submissions_postgres` e `submissions_localstack` com status `healthy`.

- [x] Verifique que a tabela foi criada:

```bash
docker exec submissions_postgres psql -U postgres -d submissions_db -c "\dt"
```

Saida esperada: tabela `submissions` listada.

- [x] Verifique que S3 bucket e SQS queue foram criados:

```bash
docker exec submissions_localstack awslocal s3 ls
docker exec submissions_localstack awslocal sqs list-queues
```

---

## Chunk 2: Platform Layer

**Branch:** `feat/platform`

### Task 8: src/platform/config.py

- [x] Crie `src/platform/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str
    aws_endpoint_url: str
    aws_default_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    s3_bucket: str
    sqs_queue_url: str
    gemini_api_key: str


settings = Settings()
```

---

### Task 9: src/platform/models.py

- [x] Crie `src/platform/models.py`:

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, Numeric, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

---

### Task 10: src/platform/database.py

- [x] Crie `src/platform/database.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.platform.config import settings

engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

---

### Task 11: src/platform/s3.py

- [x] Crie `src/platform/s3.py`:

```python
import boto3
from botocore.client import BaseClient

from src.platform.config import settings


def _client() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def upload_text(s3_key: str, text: str) -> None:
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


def download_text(s3_key: str) -> str:
    response = _client().get_object(Bucket=settings.s3_bucket, Key=s3_key)
    return response["Body"].read().decode("utf-8")
```

---

### Task 12: src/platform/sqs.py

- [x] Crie `src/platform/sqs.py`:

```python
import json

import boto3
from botocore.client import BaseClient

from src.platform.config import settings


def _client() -> BaseClient:
    return boto3.client(
        "sqs",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def publish_message(submission_id: str) -> None:
    _client().send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({"submission_id": submission_id}),
    )


def receive_messages(
    max_messages: int = 1,
    visibility_timeout: int = 120,
    wait_seconds: int = 20,
) -> list[dict]:
    response = _client().receive_message(
        QueueUrl=settings.sqs_queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=visibility_timeout,
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    _client().delete_message(
        QueueUrl=settings.sqs_queue_url,
        ReceiptHandle=receipt_handle,
    )
```

---

### Task 13: Verificar platform

- [x] Abra um shell Python e valide as importacoes:

```bash
uv run python -c "
from src.platform.config import settings
from src.platform.database import engine, async_session_factory, get_db
from src.platform.models import Submission
from src.platform import s3, sqs
print('Platform OK')
print('DB URL:', settings.database_url[:30], '...')
"
```

Saida esperada: `Platform OK` sem erros de importacao.

---

## Chunk 3: Feature — create_submission

**Branch:** `feat/create-submission`

### Task 14: src/features/submissions/create_submission/schemas.py

- [x] Crie `src/features/submissions/create_submission/schemas.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateSubmissionRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=10_000)


class CreateSubmissionResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### Task 15: src/features/submissions/create_submission/handler.py

- [x] Crie `src/features/submissions/create_submission/handler.py`:

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.platform import s3, sqs
from src.platform.models import Submission


async def create_submission(
    request: CreateSubmissionRequest,
    db: AsyncSession,
) -> CreateSubmissionResponse:
    submission_id = uuid.uuid4()
    s3_key = f"submissions/{submission_id}.txt"

    s3.upload_text(s3_key, request.text)

    submission = Submission(
        id=submission_id,
        student_id=request.student_id,
        s3_key=s3_key,
        status="PENDING",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    sqs.publish_message(str(submission_id))

    return CreateSubmissionResponse.model_validate(submission)
```

---

### Task 16: src/features/submissions/create_submission/router.py

- [x] Crie `src/features/submissions/create_submission/router.py`:

```python
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.handler import create_submission
from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.platform.database import get_db


def setup(router: APIRouter) -> None:
    @router.post("/", response_model=CreateSubmissionResponse, status_code=201)
    async def create_submission_endpoint(
        request: CreateSubmissionRequest,
        response: Response,
        db: AsyncSession = Depends(get_db),
    ) -> CreateSubmissionResponse:
        result = await create_submission(request, db)
        response.headers["Location"] = f"/api/v1/submissions/{result.id}"
        return result
```

---

### Task 17: src/main.py (skeleton com create)

- [x] Crie `src/main.py`:

```python
from fastapi import FastAPI
from fastapi.routing import APIRouter

from src.features.submissions.create_submission.router import setup as setup_create

app = FastAPI(title="Submissions Service", version="1.0.0")

router = APIRouter(prefix="/api/v1/submissions")

setup_create(router)

# get_submission e list_submissions serao adicionados nas proximas features

app.include_router(router)
```

- [x] Verifique que a API sobe:

```bash
uv run uvicorn src.main:app --reload --port 8000
```

Saida esperada: `Application startup complete.` sem erros.

- [x] Teste o endpoint (em outro terminal):

```bash
curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "aluno-001", "text": "Esta e minha redacao de teste."}' | python3 -m json.tool
```

Saida esperada: JSON com `id`, `student_id`, `status: "PENDING"`, `created_at`.

- [x] Verifique o header `Location`:

```bash
curl -si -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "aluno-001", "text": "Esta e minha redacao."}' | grep -i location
```

Saida esperada: `location: /api/v1/submissions/<uuid>`.

- [x] Verifique que o objeto foi salvo no S3:

```bash
docker exec submissions_localstack awslocal s3 ls s3://submissions-bucket/submissions/
```

Saida esperada: arquivo `.txt` listado.

- [x] Verifique que a mensagem foi enviada para o SQS:

```bash
docker exec submissions_localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/submissions-queue \
  --attribute-names ApproximateNumberOfMessages
```

Saida esperada: `ApproximateNumberOfMessages: 1`.

---

## Chunk 4: Features — get_submission e list_submissions

**Branch:** `feat/get-submission` e `feat/list-submissions` (podem ser branches separadas ou uma so)

### Task 18: src/features/submissions/get_submission/schemas.py

- [x] Crie `src/features/submissions/get_submission/schemas.py`:

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class CriterionResult(BaseModel):
    score: float
    feedback: str


class SubmissionDetailResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    s3_key: str
    status: str
    score: Decimal | None
    criteria: dict[str, Any] | None
    overall_feedback: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

### Task 19: src/features/submissions/get_submission/handler.py

- [x] Crie `src/features/submissions/get_submission/handler.py`:

```python
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.get_submission.schemas import SubmissionDetailResponse
from src.platform.models import Submission


async def get_submission(
    submission_id: uuid.UUID,
    db: AsyncSession,
) -> SubmissionDetailResponse:
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return SubmissionDetailResponse.model_validate(submission)
```

---

### Task 20: src/features/submissions/get_submission/router.py

- [x] Crie `src/features/submissions/get_submission/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.get_submission.handler import get_submission
from src.features.submissions.get_submission.schemas import SubmissionDetailResponse
from src.platform.database import get_db


def setup(router: APIRouter) -> None:
    @router.get("/{submission_id}", response_model=SubmissionDetailResponse)
    async def get_submission_endpoint(
        submission_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
    ) -> SubmissionDetailResponse:
        return await get_submission(submission_id, db)
```

---

### Task 21: src/features/submissions/list_submissions/schemas.py

- [x] Crie `src/features/submissions/list_submissions/schemas.py`:

```python
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    student_id: str
    status: str
    score: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListSubmissionsResponse(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    per_page: int
```

---

### Task 22: src/features/submissions/list_submissions/handler.py

- [x] Crie `src/features/submissions/list_submissions/handler.py`:

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.list_submissions.schemas import (
    ListSubmissionsResponse,
    SubmissionSummary,
)
from src.platform.models import Submission


async def list_submissions(
    student_id: str,
    page: int,
    per_page: int,
    db: AsyncSession,
) -> ListSubmissionsResponse:
    offset = (page - 1) * per_page

    count_result = await db.execute(
        select(func.count()).select_from(Submission).where(
            Submission.student_id == student_id
        )
    )
    total = count_result.scalar_one()

    rows = await db.execute(
        select(Submission)
        .where(Submission.student_id == student_id)
        .order_by(Submission.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    submissions = rows.scalars().all()

    return ListSubmissionsResponse(
        items=[SubmissionSummary.model_validate(s) for s in submissions],
        total=total,
        page=page,
        per_page=per_page,
    )
```

---

### Task 23: src/features/submissions/list_submissions/router.py

- [x] Crie `src/features/submissions/list_submissions/router.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.list_submissions.handler import list_submissions
from src.features.submissions.list_submissions.schemas import ListSubmissionsResponse
from src.platform.database import get_db


def setup(router: APIRouter) -> None:
    @router.get("/", response_model=ListSubmissionsResponse)
    async def list_submissions_endpoint(
        student_id: str = Query(..., description="ID do aluno"),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
    ) -> ListSubmissionsResponse:
        return await list_submissions(student_id, page, per_page, db)
```

---

### Task 24: Atualizar src/main.py com todos os slices

- [x] Atualize `src/main.py`:

```python
from fastapi import FastAPI
from fastapi.routing import APIRouter

from src.features.submissions.create_submission.router import setup as setup_create
from src.features.submissions.get_submission.router import setup as setup_get
from src.features.submissions.list_submissions.router import setup as setup_list

app = FastAPI(title="Submissions Service", version="1.0.0")

router = APIRouter(prefix="/api/v1/submissions")

# Ordem importa: list (GET /) deve ser registrado antes de get (GET /{id})
# para garantir que "/" nao seja capturado pelo path parameter
setup_create(router)
setup_list(router)
setup_get(router)

app.include_router(router)
```

- [x] Reinicie a API e teste os 3 endpoints:

```bash
# 1. Criar submission
SUBMISSION_ID=$(curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "aluno-001", "text": "Minha redacao sobre tecnologia e inovacao."}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "ID criado: $SUBMISSION_ID"

# 2. Buscar por ID
curl -s http://localhost:8000/api/v1/submissions/$SUBMISSION_ID | python3 -m json.tool

# 3. Listar por aluno
curl -s "http://localhost:8000/api/v1/submissions/?student_id=aluno-001&page=1&per_page=10" | python3 -m json.tool
```

Saida esperada para cada:
1. `201` com body contendo `id`, `status: "PENDING"`
2. `200` com todos os campos (score=null enquanto PENDING)
3. `200` com `items`, `total`, `page`, `per_page`

- [x] Teste o 404:

```bash
curl -s http://localhost:8000/api/v1/submissions/00000000-0000-0000-0000-000000000000 | python3 -m json.tool
```

Saida esperada: `{"detail": "Submission not found"}` com status 404.

---

## Chunk 5: Worker — grade_submission

**Branch:** `feat/worker`

### Task 25: src/worker/grade_submission/schemas.py

- [x] Crie `src/worker/grade_submission/schemas.py`:

```python
from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str


class GradingResult(BaseModel):
    score: float = Field(ge=0, le=10)
    criteria: dict[str, CriterionResult]
    overall_feedback: str
```

---

### Task 26: src/worker/grade_submission/grader.py

- [x] Crie `src/worker/grade_submission/grader.py`:

```python
from google import genai

from src.platform.config import settings
from src.worker.grade_submission.schemas import GradingResult

_PROMPT_TEMPLATE = """\
Voce e um avaliador experiente de redacoes escolares. Avalie a redacao abaixo com \
rigor, imparcialidade e criterio pedagogico.

Avalie os seguintes criterios, cada um com nota de 0 a 10 e feedback construtivo:
- grammar: correcao gramatical e ortografica
- coherence: coerencia e coesao textual
- argumentation: qualidade dos argumentos e desenvolvimento das ideias
- vocabulary: riqueza e adequacao do vocabulario

Calcule a nota final como media dos 4 criterios.

Redacao a avaliar:
{text}
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def grade(text: str) -> GradingResult:
    response = _get_client().models.generate_content(
        model="gemini-2.0-flash",
        contents=_PROMPT_TEMPLATE.format(text=text),
        config={
            "response_mime_type": "application/json",
            "response_json_schema": GradingResult.model_json_schema(),
        },
    )
    return GradingResult.model_validate_json(response.text)
```

---

### Task 27: src/worker/grade_submission/handler.py

- [x] Crie `src/worker/grade_submission/handler.py`:

```python
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.platform import s3
from src.platform.database import async_session_factory
from src.platform.models import Submission
from src.worker.grade_submission.grader import grade


async def process(message: dict) -> None:
    body = json.loads(message["Body"])
    submission_id = uuid.UUID(body["submission_id"])

    async with async_session_factory() as db:
        result = await db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        submission = result.scalar_one_or_none()

        if not submission:
            return

        # Idempotency: ignora se ja foi processado
        if submission.status != "PENDING":
            return

        await db.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(status="PROCESSING", updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

        try:
            text = s3.download_text(submission.s3_key)
            grading = grade(text)

            await db.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(
                    status="GRADED",
                    score=grading.score,
                    criteria={
                        k: v.model_dump() for k, v in grading.criteria.items()
                    },
                    overall_feedback=grading.overall_feedback,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            print(f"[worker] submission {submission_id} graded — score: {grading.score}")

        except Exception as exc:
            print(f"[worker] ERROR grading {submission_id}: {exc}")
            await db.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(status="ERROR", updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
```

---

### Task 28: src/worker/grade_submission/consumer.py

- [x] Crie `src/worker/grade_submission/consumer.py`:

```python
import asyncio

from src.platform import sqs
from src.worker.grade_submission.handler import process


def setup() -> None:
    """Entry point VSA: inicia o loop de consumo SQS."""
    asyncio.run(_poll_loop())


async def _poll_loop() -> None:
    print("[worker] Started. Polling SQS...")
    while True:
        messages = sqs.receive_messages(
            max_messages=1,
            visibility_timeout=120,
            wait_seconds=20,
        )

        if not messages:
            continue

        for message in messages:
            try:
                await process(message)
            finally:
                sqs.delete_message(message["ReceiptHandle"])
```

---

### Task 29: src/worker.py

- [x] Crie `src/worker.py`:

```python
from src.worker.grade_submission.consumer import setup

if __name__ == "__main__":
    setup()
```

---

### Task 30: Testar o worker end-to-end

- [x] Em terminal 1 (API rodando):

```bash
uv run uvicorn src.main:app --reload --port 8000
```

- [x] Em terminal 2 (worker):

```bash
uv run python -m src.worker
```

- [x] Em terminal 3, crie uma submission e acompanhe o ciclo completo:

```bash
# Criar
SUBMISSION_ID=$(curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "aluno-teste", "text": "A tecnologia tem transformado a sociedade de maneira profunda e irreversivel. As inovacoes digitais criaram novas formas de comunicacao, trabalho e aprendizado. Contudo, e necessario refletir sobre os impactos sociais e eticos dessas mudancas, garantindo que o progresso tecnologico beneficie a todos, e nao apenas uma parcela privilegiada da populacao."}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Submission ID: $SUBMISSION_ID"

# Aguardar alguns segundos e checar o status
sleep 5
curl -s http://localhost:8000/api/v1/submissions/$SUBMISSION_ID | python3 -m json.tool
```

Saida esperada: status `GRADED`, `score` preenchido, `criteria` com os 4 criterios, `overall_feedback`.

---

## Chunk 6: README

**Branch:** `feat/readme`

### Task 31: README.md

- [x] Substitua o conteudo de `README.md`:

```markdown
# Submissions Service

Micro-servico REST para registro e correcao de redacoes com IA (Google Gemini Flash).

## Stack

- **Python 3.13** + **uv** (gerenciador de pacotes)
- **FastAPI 0.135** — 3 endpoints REST
- **SQLAlchemy 2.0 (async) + asyncpg** — acesso ao Postgres
- **Postgres 17** — persistencia SQL
- **LocalStack 4.0** — S3 e SQS locais
- **boto3** — upload/download S3, publish/consume SQS
- **Google Gemini Flash** (`google-genai`) — correcao via IA com JSON estruturado
- **Arquitetura:** Vertical Slice Architecture (VSA)

## Pre-requisitos

- Docker e Docker Compose
- Python 3.13
- uv (`pip install uv` ou `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Chave da API Gemini (https://aistudio.google.com/app/apikey)

## Rodando Localmente

### 1. Clone e configure o ambiente

```bash
git clone <repo-url>
cd uds-test

cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY
```

### 2. Suba a infraestrutura

```bash
docker compose up -d
# Aguarde os containers ficarem healthy (~15s)
docker compose ps
```

### 3. Instale as dependencias Python

```bash
uv sync
```

### 4. Inicie a API

```bash
uv run uvicorn src.main:app --reload --port 8000
```

API disponivel em: http://localhost:8000
Documentacao interativa: http://localhost:8000/docs

### 5. Inicie o Worker (em outro terminal)

```bash
uv run python -m src.worker
```

## Endpoints

### POST /api/v1/submissions/

Cria uma nova submissao de redacao.

```bash
curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "aluno-001",
    "text": "A tecnologia tem transformado a sociedade..."
  }' | python3 -m json.tool
```

Resposta `201 Created`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "status": "PENDING",
  "created_at": "2026-03-13T10:00:00Z"
}
```

### GET /api/v1/submissions/{id}

Retorna detalhes de uma submissao, incluindo nota e criterios apos correcao.

```bash
curl -s http://localhost:8000/api/v1/submissions/550e8400-e29b-41d4-a716-446655440000 \
  | python3 -m json.tool
```

Resposta `200 OK` (apos correcao):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "s3_key": "submissions/550e8400-e29b-41d4-a716-446655440000.txt",
  "status": "GRADED",
  "score": "8.50",
  "criteria": {
    "grammar": { "score": 9.0, "feedback": "Excelente gramatica." },
    "coherence": { "score": 8.0, "feedback": "Boa coesao textual." },
    "argumentation": { "score": 7.5, "feedback": "Argumentos solidos." },
    "vocabulary": { "score": 9.5, "feedback": "Vocabulario rico." }
  },
  "overall_feedback": "Redacao de alta qualidade...",
  "created_at": "2026-03-13T10:00:00Z",
  "updated_at": "2026-03-13T10:00:05Z"
}
```

### GET /api/v1/submissions/?student_id=aluno-001

Lista submissoes de um aluno com paginacao.

```bash
curl -s "http://localhost:8000/api/v1/submissions/?student_id=aluno-001&page=1&per_page=10" \
  | python3 -m json.tool
```

Resposta `200 OK`:
```json
{
  "items": [...],
  "total": 3,
  "page": 1,
  "per_page": 10
}
```

## Arquitetura na AWS

Em producao, este servico seria implantado com os seguintes componentes AWS:

**API Gateway + Lambda:** Os 3 endpoints REST seriam expostos via API Gateway, cada um acionando uma funcao Lambda separada (create, get, list). O Lambda executa o mesmo codigo Python, com o handler adaptado para o formato de evento do API Gateway (usando `Mangum` ou similar). A separacao por funcao permite escalonamento e permissoes independentes.

**S3:** O bucket S3 armazena os textos das redacoes. O Lambda de criacao faz upload direto via boto3. As permissoes sao gerenciadas via IAM Role associada ao Lambda, sem credenciais hardcoded.

**SQS:** A fila SQS desacopla a criacao da correcao. O Lambda de criacao publica uma mensagem. Um Lambda de worker e acionado automaticamente pelo SQS Event Source Mapping, processando uma mensagem por invocacao. A fila possui DLQ (Dead Letter Queue) configurada para 3 tentativas, garantindo que falhas nao percam mensagens.

**RDS Postgres:** O banco de dados seria o Amazon RDS for PostgreSQL (Multi-AZ para alta disponibilidade). A conexao usa o pool de conexoes via RDS Proxy para evitar esgotamento de conexoes em ambiente serverless.

## Escalabilidade e Observabilidade

**Escalabilidade:** Lambda escala automaticamente ate 1.000 execucoes concorrentes por padrao. O SQS suporta throughput virtualmente ilimitado. O RDS Proxy gerencia o pool de conexoes evitando sobrecarga no banco. Para picos maiores, o concurrency limit do Lambda pode ser ajustado.

**Logs:** Todas as funcoes Lambda enviam logs automaticamente para o CloudWatch Logs. O worker loga cada mensagem processada com submission_id e status final.

**Retries e DLQ:** O SQS possui visibility timeout de 120s (suficiente para a chamada ao Gemini). Apos 3 falhas, a mensagem vai para a DLQ, onde pode ser inspecionada e reprocessada manualmente. O worker implementa verificacao de idempotencia (status != PENDING) para processar mensagens duplicadas com seguranca.

**Alertas:** CloudWatch Alarms podem ser configurados para: erros Lambda acima de threshold, mensagens na DLQ, latencia do API Gateway, e conexoes do RDS acima do limite.
