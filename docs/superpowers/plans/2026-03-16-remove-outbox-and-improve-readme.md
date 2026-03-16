# Remove Outbox Pattern & Improve README — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover o Transactional Outbox Pattern do codigo, simplificando o fluxo para S3 → DB → SQS direto no handler, e reescrever o README com documentacao detalhada da arquitetura AWS mencionando o outbox como decisao de producao.

**Architecture:** O fluxo de criacao passa de "DB insert + outbox event → relay worker → S3 + SQS" para "S3 upload → DB insert → SQS publish" diretamente no handler. O grade_submission worker permanece inalterado. A complexidade de 3 processos (API + outbox_relay + grade_worker) cai para 2 (API + grade_worker).

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, boto3, LocalStack, google-genai, Docker Compose.

> **IMPORTANTE:** O assistente NAO faz commits nem git add. O usuario controla o versionamento.

---

## File Map — Mudancas

```
MODIFICAR:
  schema.sql                                          — remove tabela outbox_events, remove coluna retry_count
  src/infra/models.py                                 — remove classe OutboxEvent, remove retry_count do Submission
  src/features/submissions/create_submission/handler.py — fluxo direto: S3 → DB → SQS (sem outbox)
  docker-compose.yml                                  — remove servico outbox_relay worker
  README.md                                           — reescrita completa com arquitetura AWS detalhada

DELETAR:
  src/workers/outbox_relay/__init__.py                — diretorio inteiro do outbox relay
  src/workers/outbox_relay/relay.py                   — diretorio inteiro do outbox relay

SEM ALTERACAO:
  src/infra/config.py
  src/infra/database.py
  src/infra/s3.py
  src/infra/sqs.py
  src/infra/types.py
  src/features/submissions/create_submission/schemas.py
  src/features/submissions/create_submission/router.py
  src/features/submissions/get_submission/*
  src/features/submissions/list_submissions/*
  src/workers/grade_submission/*
  src/main.py
  Dockerfile
  pyproject.toml
  .env.example
  scripts/init-aws.sh
```

---

## Chunk 1: Remover Outbox do Codigo

### Task 1: Remover tabela outbox_events e coluna retry_count do schema.sql

**Files:**
- Modify: `schema.sql`

- [ ] **Step 1: Editar schema.sql**

Conteudo final do arquivo:

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

Removidos:
- Coluna `retry_count INT NOT NULL DEFAULT 0` da tabela `submissions`
- Tabela `outbox_events` inteira

- [ ] **Step 2: Verificar que o SQL e valido**

Run: `docker exec submissions_postgres psql -U postgres -d submissions_db -c "SELECT 1;"`
Expected: query retorna 1 sem erro (valida conectividade)

> Nota: o schema.sql so e executado na criacao do banco. Para aplicar as mudancas localmente, use `uv run reset-db` ou recrie os containers com `docker compose down -v && docker compose up -d`.

---

### Task 2: Remover OutboxEvent e retry_count do models.py

**Files:**
- Modify: `src/infra/models.py`

- [ ] **Step 1: Editar src/infra/models.py**

Conteudo final do arquivo:

```python
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SubmissionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    GRADED = "GRADED"
    ERROR = "ERROR"


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        String(20), nullable=False, default=SubmissionStatus.PENDING
    )
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

Removidos:
- Import `Integer` do sqlalchemy
- Classe `OutboxEvent` inteira
- Campo `retry_count` do `Submission`

---

### Task 3: Simplificar create_submission handler (fluxo direto)

**Files:**
- Modify: `src/features/submissions/create_submission/handler.py`

- [ ] **Step 1: Editar src/features/submissions/create_submission/handler.py**

Conteudo final do arquivo:

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.infra import s3, sqs
from src.infra.models import Submission, SubmissionStatus


async def create_submission(
    request: CreateSubmissionRequest,
    db: AsyncSession,
) -> CreateSubmissionResponse:
    submission_id = uuid.uuid4()
    s3_key = f"submissions/{submission_id}.txt"

    await s3.upload_text(s3_key, request.text)

    submission = Submission(
        id=submission_id,
        student_id=request.student_id,
        s3_key=s3_key,
        status=SubmissionStatus.PENDING,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    await sqs.publish_message(str(submission_id))

    return CreateSubmissionResponse.model_validate(submission)
```

Mudancas:
- Adicionados imports de `s3`, `sqs` e `SubmissionStatus`
- Removido import de `OutboxEvent`
- Fluxo agora: S3 upload → DB insert → SQS publish (direto, sem outbox)
- O `s3_key` salvo no banco aponta para um objeto que JA existe no S3

---

### Task 4: Deletar diretorio outbox_relay

**Files:**
- Delete: `src/workers/outbox_relay/__init__.py`
- Delete: `src/workers/outbox_relay/relay.py`

- [ ] **Step 1: Remover o diretorio inteiro**

```bash
rm -rf src/workers/outbox_relay/
```

---

### Task 5: Remover servico outbox_relay do docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Editar docker-compose.yml**

Conteudo final do arquivo:

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

  grade-worker:
    build: .
    container_name: submissions_grade_worker
    environment:
      PYTHONUNBUFFERED: "1"
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/submissions_db
      AWS_ENDPOINT_URL: http://localstack:4566
      AWS_DEFAULT_REGION: us-east-1
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
      S3_BUCKET: submissions-bucket
      SQS_QUEUE_URL: http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/submissions-queue
      GEMINI_API_KEY: ${GEMINI_API_KEY}
    command: ["uv", "run", "python", "-m", "src.workers.grade_submission.consumer"]
    depends_on:
      postgres:
        condition: service_healthy
      localstack:
        condition: service_healthy
```

Mudancas:
- Removido o YAML anchor `x-worker-common` (nao faz sentido com 1 worker so)
- Removido servico `worker` (outbox_relay)
- Servico `grade-worker` agora tem as env vars inline (sem anchor)

---

### Task 6: Verificar que tudo compila e roda

- [ ] **Step 1: Verificar imports**

Run:
```bash
uv run python -c "
from src.infra.models import Submission, SubmissionStatus, Base
from src.features.submissions.create_submission.handler import create_submission
from src.workers.grade_submission.consumer import main
print('All imports OK')
"
```

Expected: `All imports OK` sem erros

- [ ] **Step 2: Verificar que o outbox nao e mais referenciado**

Run:
```bash
grep -r "outbox\|OutboxEvent\|outbox_relay\|retry_count" src/ --include="*.py"
```

Expected: nenhum resultado

- [ ] **Step 3: Rodar linter e type checker**

Run:
```bash
uv run ruff check src/ && uv run pyright src/
```

Expected: sem erros

---

## Chunk 2: Reescrever README.md

### Task 7: README.md completo

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Substituir conteudo completo do README.md**

```markdown
# Submissions Service

Micro-servico REST para registro e correcao automatica de redacoes com IA (Google Gemini Flash).

## Stack

| Tecnologia | Uso |
|---|---|
| Python 3.13 + uv | Runtime e gerenciamento de pacotes |
| FastAPI 0.135 | Framework REST com validacao Pydantic |
| SQLAlchemy 2.0 (async) + asyncpg | ORM assincrono com PostgreSQL |
| PostgreSQL 17 | Banco de dados relacional |
| LocalStack 4.0 | Emulacao local de S3 e SQS |
| boto3 | SDK AWS para S3 e SQS |
| Google Gemini 2.5 Flash Lite | Correcao de redacoes via IA com JSON estruturado |
| Docker Compose | Orquestracao da infraestrutura local |

**Arquitetura:** Vertical Slice Architecture (VSA) — codigo organizado por feature/use-case, nao por camada tecnica.

## Como Funciona

```
Aluno envia redacao
        |
        v
  POST /api/v1/submissions/
        |
        +-- 1. Upload do texto no S3
        +-- 2. INSERT no Postgres (status: PENDING)
        +-- 3. Publica submission_id no SQS
        |
        v
  Grade Worker (daemon)
        |
        +-- 1. Consome mensagem do SQS
        +-- 2. Baixa texto do S3
        +-- 3. Envia para Gemini Flash (structured output)
        +-- 4. Atualiza Postgres: status GRADED, nota, criterios, feedback
        +-- 5. Deleta mensagem do SQS
        |
        v
  GET /api/v1/submissions/{id}  -->  Retorna nota + criterios + feedback
```

### Status da Submission

| Status | Descricao |
|---|---|
| `PENDING` | Criada, aguardando processamento pelo worker |
| `PROCESSING` | Worker iniciou a correcao |
| `GRADED` | Correcao concluida com nota e feedback |
| `ERROR` | Falha na correcao (Gemini indisponivel, parsing, etc.) |

Transicoes: `PENDING` → `PROCESSING` → `GRADED` | `ERROR`

### Criterios de Avaliacao

O Gemini avalia cada redacao em 4 criterios com nota de 0 a 10:

| Criterio | O que avalia |
|---|---|
| `grammar` | Correcao gramatical e ortografica |
| `coherence` | Coerencia e coesao textual |
| `argumentation` | Qualidade dos argumentos e desenvolvimento das ideias |
| `vocabulary` | Riqueza e adequacao do vocabulario |

A nota final e a media dos 4 criterios.

## Pre-requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose
- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Chave de API do Gemini — obtenha em [aistudio.google.com](https://aistudio.google.com/app/apikey)

## Rodando Localmente

### 1. Clone e configure

```bash
git clone <repo-url>
cd uds-test

cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY com sua chave
```

### 2. Suba a infraestrutura

```bash
docker compose up -d
```

Aguarde os containers ficarem healthy (~15-20s):

```bash
docker compose ps
```

Containers esperados:
- `submissions_postgres` — healthy
- `submissions_localstack` — healthy
- `submissions_grade_worker` — running

### 3. Instale as dependencias

```bash
uv sync
```

### 4. Inicie a API

```bash
uv run start
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Endpoints

### POST /api/v1/submissions/

Registra uma nova redacao para correcao.

```bash
curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "aluno-001",
    "text": "A tecnologia tem transformado a sociedade de maneira profunda e irreversivel. As inovacoes digitais criaram novas formas de comunicacao, trabalho e aprendizado. Contudo, e necessario refletir sobre os impactos sociais e eticos dessas mudancas, garantindo que o progresso tecnologico beneficie a todos, e nao apenas uma parcela privilegiada da populacao."
  }' | python3 -m json.tool
```

**Resposta — 201 Created:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "status": "PENDING",
  "created_at": "2026-03-15T10:00:00-03:00"
}
```

O header `Location` aponta para o recurso criado: `Location: /api/v1/submissions/{id}`

**Validacao:**
- `student_id`: obrigatorio, 1-100 caracteres
- `text`: obrigatorio, 1-10.000 caracteres

---

### GET /api/v1/submissions/{id}

Retorna os detalhes de uma submission, incluindo nota e criterios apos a correcao.

```bash
curl -s http://localhost:8000/api/v1/submissions/550e8400-e29b-41d4-a716-446655440000 \
  | python3 -m json.tool
```

**Resposta — 200 OK (apos correcao):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "s3_key": "submissions/550e8400-e29b-41d4-a716-446655440000.txt",
  "status": "GRADED",
  "score": "8.50",
  "criteria": {
    "grammar":        { "score": 9.0, "feedback": "Excelente gramatica, sem erros significativos." },
    "coherence":      { "score": 8.0, "feedback": "Boa coesao textual com conectivos adequados." },
    "argumentation":  { "score": 7.5, "feedback": "Argumentos solidos, mas poderiam ser mais aprofundados." },
    "vocabulary":     { "score": 9.5, "feedback": "Vocabulario rico e variado." }
  },
  "overall_feedback": "Redacao de alta qualidade com argumentacao bem estruturada e vocabulario adequado ao tema.",
  "created_at": "2026-03-15T10:00:00-03:00",
  "updated_at": "2026-03-15T10:00:05-03:00"
}
```

Retorna `404 Not Found` se o ID nao existir.

---

### GET /api/v1/submissions/?student_id=aluno-001

Lista submissions de um aluno com paginacao (ordenadas por data decrescente).

```bash
curl -s "http://localhost:8000/api/v1/submissions/?student_id=aluno-001&page=1&per_page=10" \
  | python3 -m json.tool
```

**Resposta — 200 OK:**
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "student_id": "aluno-001",
      "status": "GRADED",
      "score": "8.50",
      "created_at": "2026-03-15T10:00:00-03:00",
      "updated_at": "2026-03-15T10:00:05-03:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10
}
```

**Parametros de query:**

| Parametro    | Tipo   | Padrao | Descricao                 |
|-------------|--------|--------|---------------------------|
| `student_id` | string | —      | ID do aluno (obrigatorio) |
| `page`       | int    | 1      | Pagina (minimo: 1)        |
| `per_page`   | int    | 10     | Itens por pagina (1-100)  |

## Banco de Dados

### Schema

```sql
CREATE TABLE submissions (
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
```

### Indices

- `idx_submissions_student_id` — acelera filtro por aluno no `GET /submissions/?student_id=`
- `idx_submissions_student_id_created_at` — indice composto que otimiza a listagem paginada por aluno ordenada por data

## Estrutura do Projeto

```
uds-test/
  docker-compose.yml              # Postgres + LocalStack + Grade Worker
  Dockerfile                      # Imagem Python para workers
  schema.sql                      # DDL do banco
  pyproject.toml                  # Dependencias (uv)
  .env.example                    # Variaveis de ambiente documentadas
  scripts/
    init-aws.sh                   # Cria bucket S3 e fila SQS no LocalStack
  src/
    main.py                       # Entry point FastAPI (composition root)
    infra/
      config.py                   # Settings via pydantic-settings
      database.py                 # Engine + session factory async
      models.py                   # SQLAlchemy model: Submission
      s3.py                       # Wrapper boto3: upload/download texto
      sqs.py                      # Wrapper boto3: publish/receive/delete
      types.py                    # Tipos customizados (BRTDatetime)
    features/
      submissions/
        create_submission/        # POST /api/v1/submissions/
          router.py               # Entry point VSA: setup(router)
          handler.py              # S3 upload + DB insert + SQS publish
          schemas.py              # Request/Response Pydantic models
        get_submission/           # GET /api/v1/submissions/{id}
          router.py
          handler.py
          schemas.py
        list_submissions/         # GET /api/v1/submissions/?student_id=
          router.py
          handler.py
          schemas.py
    workers/
      grade_submission/           # Worker: consome SQS e corrige via Gemini
        consumer.py               # SQS poll loop
        handler.py                # Orquestra: DB + S3 + Gemini + DB update
        grader.py                 # Chamada Gemini com structured output
        schemas.py                # GradingResult, CriterionResult
```

A arquitetura segue **Vertical Slice Architecture (VSA)**: cada feature tem seu proprio diretorio com router, handler e schemas. Nao ha camada de servico compartilhada nem repository generico — cada slice e autocontido. O worker e tratado como um event consumer slice.

## Arquitetura na AWS (Producao)

Em producao, este servico seria implantado com componentes AWS nativos, mantendo a mesma logica de negocio. O codigo Python permanece identico — apenas os entry points e a infraestrutura de conexao mudam.

### API Gateway + Lambda

Os 3 endpoints REST seriam expostos via **API Gateway HTTP** (nao REST API, que e mais caro e lento), cada um acionando uma funcao **Lambda** separada (create, get, list). O handler FastAPI seria adaptado para o formato de evento do API Gateway usando o adapter [Mangum](https://github.com/jordanerr/mangum), que converte o evento Lambda em uma request ASGI transparentemente.

A separacao por funcao Lambda permite:
- **Escalonamento independente** — o endpoint de criacao pode escalar separadamente dos de leitura
- **Permissoes IAM granulares** — o Lambda de create precisa de `s3:PutObject` e `sqs:SendMessage`, enquanto os de leitura so precisam de acesso ao RDS
- **Cold start reduzido** — funcoes menores com menos dependencias inicializam mais rapido

### S3

O bucket S3 armazena os textos das redacoes no mesmo padrao de chave usado localmente: `submissions/{uuid}.txt`. O Lambda de criacao faz upload direto via boto3. As permissoes sao gerenciadas via **IAM Role** associada ao Lambda — sem credenciais hardcoded, sem variavel `AWS_ACCESS_KEY_ID`. O bucket teria:
- **Lifecycle Policy** para mover textos antigos para S3 Glacier apos 90 dias
- **Server-Side Encryption** (SSE-S3) para dados em repouso
- **Bucket Policy** restritiva permitindo acesso apenas dos Lambdas e do worker

### SQS + Lambda Event Source Mapping

A fila SQS desacopla criacao e correcao. O Lambda de criacao publica uma mensagem com o `submission_id`. Um **Lambda de worker** e acionado automaticamente pelo **SQS Event Source Mapping** — substituindo o daemon de polling local. Cada invocacao processa uma mensagem (batch size = 1 para manter o timeout confortavel com a chamada ao Gemini).

Configuracoes da fila:
- **Visibility Timeout: 180s** (1.5x o tempo maximo esperado de correcao pelo Gemini)
- **maxReceiveCount: 3** — apos 3 falhas, a mensagem vai para a DLQ
- **Dead Letter Queue (DLQ)** — fila separada para mensagens que falharam apos 3 tentativas, permitindo inspecao manual e reprocessamento

### RDS PostgreSQL

O banco seria o **Amazon RDS for PostgreSQL** (Multi-AZ para alta disponibilidade). A conexao usa **RDS Proxy** para gerenciar o pool de conexoes — essencial em ambiente serverless onde cada invocacao Lambda pode abrir novas conexoes, potencialmente esgotando o limite do banco.

### Transactional Outbox Pattern (consideracao de producao)

Na implementacao local, o handler faz S3 upload → DB insert → SQS publish sequencialmente. Isso e adequado para o ambiente de desenvolvimento, mas em producao existe um risco: se o processo falhar **entre** o DB insert e o SQS publish, a submission ficaria no banco com status PENDING mas sem mensagem na fila — nunca seria corrigida.

Para resolver isso em producao, o ideal seria o **Transactional Outbox Pattern**:

1. O handler faz S3 upload e depois salva a `Submission` + um `OutboxEvent` na **mesma transacao** do banco (atomicidade garantida pelo ACID do Postgres)
2. Um **relay worker** (ou EventBridge Scheduler + Lambda) faz polling na tabela `outbox_events` usando `SELECT FOR UPDATE SKIP LOCKED` para processamento concurrency-safe
3. O relay publica a mensagem no SQS e deleta o evento da tabela outbox
4. Se o relay falhar, o evento permanece na tabela e sera reprocessado na proxima iteracao

Essa abordagem garante **exatamente-uma-vez** na publicacao de mensagens (at-least-once delivery + idempotencia no consumer) sem depender de transacoes distribuidas (2PC).

## Escalabilidade e Observabilidade

### Escalabilidade

- **Lambda** escala automaticamente ate 1.000 execucoes concorrentes por regiao (ajustavel via Reserved Concurrency). Para o worker de correcao, um **concurrency limit** (ex: 10) evitaria sobrecarregar a API do Gemini
- **SQS** suporta throughput virtualmente ilimitado (standard queue) e atua como buffer natural em picos — se o volume de submissions dobrar, as mensagens aguardam na fila ate o worker processar
- **RDS Proxy** gerencia o pool de conexoes, evitando o problema de connection exhaustion tipico de serverless. Sem o proxy, 100 invocacoes Lambda simultaneas abririam 100 conexoes no banco
- Para volumes muito altos, o indice composto `(student_id, created_at DESC)` garante que a listagem paginada continua performatica

### Idempotencia

O grade worker verifica `status != PENDING` antes de processar, usando `SELECT FOR UPDATE` para lock. Isso protege contra reentregas do SQS (que garante at-least-once, nao exactly-once) sem efeitos colaterais — se a mensagem for entregue duas vezes, a segunda invocacao encontra o status como `PROCESSING` ou `GRADED` e retorna sem fazer nada.

### Retries e DLQ

- **Visibility Timeout: 180s** — se o worker nao deletar a mensagem nesse prazo (ex: timeout do Gemini), o SQS reentrega automaticamente
- **maxReceiveCount: 3** — apos 3 tentativas, a mensagem vai para a **Dead Letter Queue**
- A DLQ permite: inspecao manual do que falhou, reprocessamento em lote apos correcao do bug, alertas automaticos quando mensagens chegam
- O campo `status: ERROR` no banco complementa a DLQ — permite consultas como "quantas submissions falharam nas ultimas 24h"

### Logs e Metricas

- **CloudWatch Logs**: todas as funcoes Lambda enviam logs automaticamente. O worker loga cada mensagem processada com `submission_id` e status final (`GRADED` ou `ERROR`), permitindo rastreio end-to-end
- **Structured logging** (JSON) facilitaria a criacao de filtros e dashboards no CloudWatch Insights
- **CloudWatch Metrics**: Lambda publica automaticamente `Invocations`, `Errors`, `Duration`, `ConcurrentExecutions` e `Throttles`

### Alertas

CloudWatch Alarms recomendados:
- **Lambda Error Rate** > 5% — indica bug no codigo ou servico externo (Gemini) instavel
- **DLQ Messages** > 0 — mensagens que falharam 3x precisam de atencao
- **API Gateway 5xx** > threshold — erros no lado do servidor
- **API Gateway Latency p99** > 2s — degradacao de performance
- **RDS Connections** > 80% do limite — risco de exhaustion
- **SQS ApproximateAgeOfOldestMessage** > 5min — fila acumulando, worker possivelmente travado
```

---

### Task 8: Verificacao final

- [ ] **Step 1: Verificar que o README referencia corretamente a estrutura**

Conferir que todos os arquivos e diretorios mencionados na secao "Estrutura do Projeto" existem:

```bash
ls -la src/infra/ src/features/submissions/create_submission/ src/features/submissions/get_submission/ src/features/submissions/list_submissions/ src/workers/grade_submission/
```

- [ ] **Step 2: Verificar que nao ha referencias ao outbox no README**

```bash
grep -i "outbox_relay\|outbox_events" README.md
```

Expected: nenhum resultado (a unica mencao ao outbox e na secao "Transactional Outbox Pattern" como consideracao de producao, que usa o nome conceitual, nao nomes de arquivos/tabelas do codigo)

- [ ] **Step 3: Teste end-to-end completo**

Terminal 1 — API:
```bash
uv run start
```

Terminal 2 — verificar que o grade-worker esta rodando via Docker:
```bash
docker compose logs -f grade-worker
```

Terminal 3 — criar e acompanhar:
```bash
# Criar submission
SUBMISSION_ID=$(curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "aluno-teste", "text": "A tecnologia tem transformado a sociedade de maneira profunda e irreversivel. As inovacoes digitais criaram novas formas de comunicacao, trabalho e aprendizado."}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Submission ID: $SUBMISSION_ID"

# Aguardar correcao (~5-10s)
sleep 10

# Verificar resultado
curl -s http://localhost:8000/api/v1/submissions/$SUBMISSION_ID | python3 -m json.tool

# Listar por aluno
curl -s "http://localhost:8000/api/v1/submissions/?student_id=aluno-teste" | python3 -m json.tool
```

Expected:
- POST retorna 201 com status PENDING
- GET retorna 200 com status GRADED, score preenchido, criteria com 4 itens
- Lista retorna items com a submission criada
