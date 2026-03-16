# Submissions Service — Design Spec

## Objetivo

Micro-servico para registrar e consultar correcoes de respostas discursivas/redacoes com persistencia SQL, integracao assincrona com fila (SQS) e armazenamento (S3), usando Google Gemini Flash para correcao via IA.

## Stack

| Componente | Tecnologia | Versao |
|---|---|---|
| Runtime | Python | 3.13 |
| Package manager | uv | latest |
| Framework | FastAPI | 0.135.x |
| ASGI server | Uvicorn | 0.41.x |
| ORM | SQLAlchemy (async) | 2.0.48 |
| DB driver | asyncpg | 0.31.0 |
| DB | PostgreSQL | 17-alpine |
| Object storage | S3 via LocalStack | 4.0 |
| Message queue | SQS via LocalStack | 4.0 |
| AWS SDK | boto3 | 1.42.x |
| AI grading | google-genai | latest |
| Config | pydantic-settings | 2.13.x |
| Infra local | Docker Compose | - |

## Arquitetura

Vertical Slice Architecture (VSA) — codigo organizado por feature/use-case, nao por camada tecnica. Clean Code e DRY.

### Estrutura do Projeto

```
uds-test/
  docker-compose.yml
  schema.sql
  pyproject.toml
  .env.example
  scripts/
    init-aws.sh
  src/
    features/
      submissions/
        create_submission/
          __init__.py
          router.py
          handler.py
          schemas.py
        get_submission/
          __init__.py
          router.py
          handler.py
          schemas.py
        list_submissions/
          __init__.py
          router.py
          handler.py
          schemas.py
    platform/
      config.py
      database.py
      s3.py
      sqs.py
      models.py
    worker/
      grade_submission/
        __init__.py
        consumer.py
        handler.py
        grader.py
        schemas.py
    main.py
    worker.py
```

### Principios VSA Aplicados

- Um diretorio por feature contendo router, handler, schemas e testes
- Um entry point (`setup()`) por feature que recebe router + dependencias
- Minimizar acoplamento entre slices, maximizar dentro do slice
- Sem abstracoes prematuras — sem repository generico, sem service layer compartilhada
- `models.py` em `platform/` porque `Submission` e usada por multiplos slices (extracao justificada)
- Worker tratado como event consumer slice

## Fluxo de Dados

### POST /api/v1/submissions

1. Recebe `{ "student_id": "abc", "text": "..." }`
2. Upload do texto para S3 → gera `s3_key`
3. INSERT no Postgres com `status=PENDING`, `s3_key`, `score=null`
4. Publica mensagem no SQS com `{ "submission_id": "<uuid>" }`
5. Retorna `201` com header `Location: /api/v1/submissions/{id}`

### Worker (loop continuo)

1. Poll SQS (visibility timeout: 120s) → recebe `submission_id`
2. Busca submission no DB → pega `s3_key`
3. Verifica idempotencia: se `status != PENDING`, ignora (deleta mensagem e retorna)
4. Atualiza DB: `status=PROCESSING`
5. Baixa texto do S3
6. Envia para Gemini Flash com prompt estruturado
7. Se sucesso: atualiza DB com `status=GRADED`, `score`, `criteria` (JSONB), `overall_feedback`, `updated_at`
8. Se erro: atualiza DB com `status=ERROR`, `updated_at`
9. Deleta mensagem da fila

### Status Machine

`PENDING` → `PROCESSING` → `GRADED` | `ERROR`

- `PENDING`: submission criada, aguardando worker
- `PROCESSING`: worker pegou a mensagem, correcao em andamento
- `GRADED`: correcao concluida com sucesso
- `ERROR`: falha na correcao (Gemini indisponivel, erro de parsing, etc.)

## API REST

Todos os endpoints sob `/api/v1/submissions`. RESTful: status codes corretos, Location header no POST, recursos como substantivos. Sem HATEOAS.

### POST /api/v1/submissions

```
Request:
  { "student_id": "abc", "text": "..." }
  Validacao: student_id obrigatorio, text obrigatorio (max 10.000 caracteres)

Response: 201 Created
Headers:
  Location: /api/v1/submissions/{id}
Body:
  {
    "id": "uuid",
    "student_id": "abc",
    "status": "PENDING",
    "created_at": "2026-03-13T10:00:00Z"
  }

Errors:
  422 - Validation error (campos obrigatorios)
```

### GET /api/v1/submissions/{id}

```
Response: 200 OK
Body:
  {
    "id": "uuid",
    "student_id": "abc",
    "s3_key": "submissions/uuid.txt",
    "status": "GRADED",
    "score": 8.50,
    "criteria": {
      "grammar": { "score": 9.0, "feedback": "..." },
      "coherence": { "score": 8.0, "feedback": "..." },
      "argumentation": { "score": 7.0, "feedback": "..." },
      "vocabulary": { "score": 10.0, "feedback": "..." }
    },
    "overall_feedback": "...",
    "created_at": "2026-03-13T10:00:00Z",
    "updated_at": "2026-03-13T10:01:00Z"
  }

Errors:
  404 - Submission not found
```

### GET /api/v1/submissions?student_id=abc&page=1&per_page=10

```
Response: 200 OK
Body:
  {
    "items": [...],
    "total": 42,
    "page": 1,
    "per_page": 10
  }

Ordenacao: created_at DESC (mais recentes primeiro)

Errors:
  422 - student_id obrigatorio
```

## Banco de Dados

```sql
CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    score NUMERIC(4,2),
    criteria JSONB,
    overall_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_submissions_student_id ON submissions(student_id);
CREATE INDEX idx_submissions_student_id_created_at ON submissions(student_id, created_at DESC);
```

## Infraestrutura Local

### Docker Compose

- `postgres:17-alpine` com volume montando `schema.sql` em `/docker-entrypoint-initdb.d/`
- `localstack/localstack:4.0` com S3 e SQS, init script criando bucket e fila

### Init Script (scripts/init-aws.sh)

```bash
#!/bin/bash
awslocal s3 mb s3://submissions-bucket
awslocal sqs create-queue --queue-name submissions-queue
```

### Variaveis de Ambiente (.env)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/submissions_db
AWS_ENDPOINT_URL=http://localhost:4566
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
S3_BUCKET=submissions-bucket
SQS_QUEUE_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/submissions-queue
GEMINI_API_KEY=your-api-key-here
```

## Grader (Gemini Flash)

Usa o SDK `google-genai` com structured output via Pydantic:

```python
from google import genai
from pydantic import BaseModel, Field

class CriterionResult(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str

class GradingResult(BaseModel):
    score: float = Field(ge=0, le=10)
    criteria: dict[str, CriterionResult]
    overall_feedback: str

client = genai.Client(api_key=settings.gemini_api_key)
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt,
    config={
        "response_mime_type": "application/json",
        "response_json_schema": GradingResult.model_json_schema(),
    },
)
result = GradingResult.model_validate_json(response.text)
```

Criterios avaliados: grammar, coherence, argumentation, vocabulary. Nota final de 0 a 10.

## Paginacao

Offset/limit simples com query params `page` e `per_page`. Default: `page=1`, `per_page=10`.

## README

Deve conter:
- Instrucoes para rodar localmente (docker compose up + uvicorn + worker)
- Exemplos de curl para os 3 endpoints
- Explicacao de como o sistema seria montado na AWS (API Gateway + Lambda + SQS + S3)
- Pontos de escalabilidade e observabilidade (logs, retries, DLQ)
