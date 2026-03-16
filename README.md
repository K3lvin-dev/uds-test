# Submissions Service

Micro-serviço REST para registro e correção automática de redações escolares com inteligência artificial (Google Gemini Flash).

## Stack

| Tecnologia | Uso |
|---|---|
| Python 3.13 | Linguagem principal |
| FastAPI | Framework web / API REST |
| SQLAlchemy (async) | ORM e gerenciamento de sessões |
| asyncpg | Driver PostgreSQL assíncrono |
| PostgreSQL 17 | Banco de dados relacional |
| LocalStack 4.0 | Emulação local de S3 e SQS |
| boto3 | SDK AWS (S3 e SQS) |
| google-genai | Cliente oficial Google Gemini |
| Docker Compose | Orquestração de infraestrutura local |
| uv | Gerenciador de pacotes e ambiente virtual |

## Como Funciona

### Fluxo de Processamento

```
Cliente HTTP
     |
     | POST /submissions
     v
  FastAPI (API)
     |
     |-- 1. Faz upload do texto da redação para o S3
     |-- 2. Persiste Submission com status PENDING no PostgreSQL
     |-- 3. Publica mensagem com submission_id na fila SQS
     |
     v
  SQS (fila)
     |
     | (consome mensagem)
     v
  grade_worker
     |
     |-- 4. Atualiza status para PROCESSING
     |-- 5. Lê o texto da redação no S3
     |-- 6. Envia para o Google Gemini Flash para correção
     |-- 7. Persiste score, criteria e overall_feedback no PostgreSQL
     |-- 8. Atualiza status para GRADED (ou ERROR em caso de falha)
     |-- 9. Deleta a mensagem da fila SQS
```

### Ciclo de Vida de uma Submission

| Status | Descrição |
|---|---|
| `PENDING` | Submission criada, aguardando processamento pelo worker |
| `PROCESSING` | Worker consumiu a mensagem e está corrigindo via Gemini |
| `GRADED` | Correção concluída com sucesso |
| `ERROR` | Falha durante o processamento |

### Critérios de Avaliação

O campo `criteria` é um objeto JSONB com as seguintes dimensões, cada uma pontuada de 0 a 10:

| Critério | Descrição |
|---|---|
| `grammar` | Correção gramatical e ortográfica |
| `coherence` | Coerência e coesão textual |
| `argumentation` | Qualidade e profundidade da argumentação |
| `vocabulary` | Riqueza e adequação do vocabulário |

## Pré-requisitos

- **Docker** e **Docker Compose** instalados
- **Python 3.13** instalado
- **uv** instalado:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Chave de API do Google Gemini**: obtenha em [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

## Rodando Localmente

### 1. Clone e configure o ambiente

```bash
git clone <url-do-repositorio>
cd uds-test
cp .env.example .env
```

Abra o arquivo `.env` e preencha a variável obrigatória:

```env
GEMINI_API_KEY=sua_chave_aqui
```

### 2. Instale as dependências Python

```bash
uv sync
```

### 3. Suba a infraestrutura

O Docker Compose gerencia apenas a infraestrutura  PostgreSQL e LocalStack (S3 + SQS). A aplicação roda como processo nativo, espelhando a separação real da AWS entre serviços gerenciados e compute.

```bash
uv run infra
```

Aguarda automaticamente os containers ficarem healthy. O script `scripts/init-aws.sh` executa ao subir o LocalStack e cria o bucket S3 e a fila SQS.

### 4. Inicie a aplicação

```bash
uv run dev
```

Sobe a API e o worker juntos no mesmo terminal, com output prefixado:

```
[api]    INFO:     Application startup complete.
[api]    INFO:     Uvicorn running on http://0.0.0.0:8000
[worker] [grade_worker] Started. Polling SQS...
```

API disponível em `http://localhost:8000`  Swagger UI em `http://localhost:8000/docs`.

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| `POST` | `/api/v1/submissions/` | Cria uma submission e enfileira para correção |
| `GET` | `/api/v1/submissions/{id}` | Retorna detalhes, status e resultado da correção |
| `GET` | `/api/v1/submissions/` | Lista submissions de um aluno com paginação |

Para exemplos de uso, importe a collection Postman incluída no repositório: `submissions-service.postman_collection.json`.

## Banco de Dados

### Schema SQL

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

### Índices

| Índice | Colunas | Finalidade |
|---|---|---|
| `idx_submissions_student_id` | `student_id` | Filtragem rápida por estudante |
| `idx_submissions_student_id_created_at` | `student_id, created_at DESC` | Queries paginadas ordenadas por data de criação, cobrindo os dois campos mais acessados juntos |

O índice composto `(student_id, created_at DESC)` é especialmente relevante para o endpoint de listagem, pois elimina a necessidade de um sort separado no resultado e cobre a cláusula `WHERE student_id = ?` com ordenação decrescente em uma única varredura de índice.

## Estrutura do Projeto

```
.
├── docker-compose.yml          # Infraestrutura local: PostgreSQL e LocalStack
├── Dockerfile                  # Empacotamento para deploy (Lambda / ECS)
├── schema.sql                  # DDL do banco de dados
├── pyproject.toml              # Dependências e entry points (uv)
├── .env.example                # Variáveis de ambiente necessárias
├── scripts/
│   ├── dev.py                  # Sobe API + worker juntos (uv run dev)
│   ├── setup_infra.py          # Sobe infraestrutura Docker (uv run infra)
│   └── init-aws.sh             # Cria bucket S3 e fila SQS no LocalStack
└── src/
    ├── main.py                 # Criação da aplicação FastAPI e handler Lambda
    ├── infra/
    │   ├── config.py           # Configurações via variáveis de ambiente (pydantic-settings)
    │   ├── database.py         # Engine async e fábrica de sessões SQLAlchemy
    │   ├── models.py           # Modelo ORM Submission
    │   ├── s3.py               # Cliente S3 (upload e download)
    │   ├── sqs.py              # Cliente SQS (publish e delete)
    │   └── types.py            # Tipos compartilhados
    ├── features/
    │   └── submissions/
    │       ├── create_submission/  # POST /api/v1/submissions/
    │       ├── get_submission/     # GET /api/v1/submissions/{id}
    │       └── list_submissions/   # GET /api/v1/submissions/
    └── workers/
        └── grade_submission/
            ├── consumer.py     # Polling SQS (local) e lambda_handler (AWS)
            ├── handler.py      # Orquestra o fluxo de correção
            ├── grader.py       # Integração com Google Gemini Flash
            └── schemas.py      # Schemas internos do worker
```

### Vertical Slice Architecture (VSA)

O projeto adota Vertical Slice Architecture: cada funcionalidade (criar submission, buscar por id, listar) é isolada em seu próprio diretório com router, handler e schemas próprios. Não existe uma camada de "serviços" ou "repositórios" compartilhada. Isso reduz o acoplamento entre funcionalidades, facilita a manutenção isolada de cada slice e torna o código mais fácil de navegar  para entender o que o endpoint `POST /submissions` faz, basta abrir `features/submissions/create_submission/`.

## Arquitetura na AWS (Produção)

```
Cliente HTTP
     |
     v
[ API Gateway ]
     |
     v
[ Lambda  API ]  ───>  [ S3 ]
     |
     v
[ SQS ]
     |
     v
[ Lambda  Worker ]  ───>  [ Gemini ]
     |
     v
[ RDS Proxy ]
     |
     v
[ RDS PostgreSQL ]
```

### Passo a Passo

**1. RDS PostgreSQL**
Provisionar o banco com Multi-AZ para alta disponibilidade. Adicionar **RDS Proxy** na frente  Lambda escala rápido e abriria centenas de conexões simultâneas sem isso, esgotando o banco.

**2. S3**
Criar o bucket com criptografia SSE-S3 e acesso público bloqueado. Lifecycle Policy para mover textos já processados para Glacier após 90 dias.

**3. SQS**
Criar a fila principal e uma **DLQ** vinculada. Configurar `Visibility Timeout 180s` e `maxReceiveCount 3`  após 3 falhas seguidas, a mensagem vai automaticamente para a DLQ.

**4. Lambda (API)**
Empacotar a FastAPI com **Mangum** (adaptador ASGI → Lambda). Configurar IAM Role com permissões mínimas (S3 + SQS + RDS Proxy). Conectar ao API Gateway.

**5. API Gateway HTTP API**
Criar a HTTP API e rotear `/api/v1/submissions/*` para a Lambda da API. HTTP API é mais barata e mais rápida que REST API para esse caso de uso.

**6. Lambda (Worker)**
Deploy do `grade_worker` com **Event Source Mapping** na fila SQS (`batch size 1`). A AWS gerencia o polling automaticamente  sem necessidade de processo rodando continuamente. Configurar Concurrency Limit para não estourar os rate limits do Gemini.

## Ajustes Futuros

### Transactional Outbox

#### O problema

Hoje, criar uma submission envolve 3 operações em sequência:

```
1. Upload do texto → S3
2. INSERT da submission (status PENDING) → PostgreSQL
3. Publicar mensagem com submission_id → SQS
```

Essas 3 operações **não são atômicas**. Se a aplicação travar ou perder conexão entre o passo 2 e o 3, a submission fica gravada no banco com status `PENDING` para sempre  nunca vai ser corrigida, e o estudante não recebe nenhum retorno.

#### A solução com DynamoDB + Streams

A ideia é simples: em vez de publicar no SQS diretamente, a Lambda da API **grava um registro no DynamoDB** junto com a submission no PostgreSQL. Aí entra o **DynamoDB Streams**: é um recurso nativo da AWS que monitora a tabela e, a cada inserção, dispara automaticamente uma Lambda.

O fluxo fica assim:

```
Lambda (API)
    |
    |── INSERT submission (PENDING) ──> PostgreSQL
    |── PUT outbox_event ──────────────> DynamoDB
                                              |
                                    (DynamoDB Streams detecta o PUT)
                                              |
                                              v
                                       Lambda (Relay)
                                              |
                                              v
                                            SQS
```

O ponto chave: a Lambda da API não se preocupa mais em publicar no SQS. Ela só grava no DynamoDB  e a partir daí a AWS cuida do resto automaticamente. Não tem polling, não tem processo rodando a cada minuto, não tem cron job. O Streams é event-driven: reagiu ao INSERT, disparou, acabou.

#### Por que isso resolve o problema

Antes, a falha podia acontecer entre o INSERT no banco e o publish no SQS  uma janela de risco real. Com esse padrão, o risco fica restrito à janela entre o INSERT no PostgreSQL e o PUT no DynamoDB, que são duas operações muito rápidas e locais. E mesmo que o PUT no DynamoDB falhe, a Lambda pode fazer retry sem efeito colateral nenhum  o DynamoDB é idempotente por chave.

Não está implementado aqui porque localmente a chance de falha nessa janela é negligenciável. Em produção com tráfego real e múltiplas instâncias, valeria a pena.

### Dead Letter Queue (DLQ)

Após 3 tentativas de processamento com falha, a mensagem vai para a DLQ. Evita que uma mensagem problemática fique travando a fila indefinidamente. A DLQ serve para inspeção e reprocessamento manual após identificar a causa.

### Observabilidade

- **CloudWatch Logs**: Lambda já envia logs automaticamente. Usar JSON estruturado com `submission_id` e `student_id` para facilitar buscas no Logs Insights.
- **Alertas essenciais**: erros > 5% na Lambda do worker, qualquer mensagem na DLQ, e latência p99 > 2s no API Gateway.
