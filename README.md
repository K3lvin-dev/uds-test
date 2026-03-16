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

Esta seção descreve como o serviço seria implantado em produção na AWS. O ambiente local já replica essa separação: Docker gerencia apenas a infraestrutura (PostgreSQL e LocalStack como substitutos de RDS e S3/SQS), enquanto a aplicação roda como processo nativo  da mesma forma que na AWS o compute (Lambda) é separado dos serviços gerenciados.

### API Gateway + Lambda

A API seria exposta via **AWS API Gateway HTTP API** (não REST API). A HTTP API é significativamente mais barata e com latência menor para casos de uso padrão; a REST API oferece recursos adicionais (cache, planos de uso, API keys nativos) que não são necessários aqui.

A aplicação FastAPI seria empacotada com o adaptador **Mangum**, que converte eventos do API Gateway/Lambda em requisições ASGI compatíveis com FastAPI  sem necessidade de reescrever a aplicação.

Cada endpoint poderia ser mapeado para uma função Lambda separada, o que permite:
- IAM Roles granulares por função (princípio do menor privilégio)
- Escalabilidade independente por endpoint
- Deploys isolados sem risco de regressão em outros endpoints

O ponto de atenção é o **cold start**: funções Lambda Python têm latência de inicialização na primeira invocação após um período de inatividade. Para mitigar, recomenda-se habilitar **Provisioned Concurrency** nos endpoints mais críticos ou usar Lambda SnapStart (disponível para runtimes Java, mas não Python nativamente).

### S3

O padrão de chave `submissions/{submission_id}.txt` se mantém idêntico ao ambiente local.

Em produção:
- A função Lambda assumiria uma **IAM Role** com permissão `s3:PutObject` e `s3:GetObject` restritas ao bucket específico  sem credenciais hardcoded no código ou variáveis de ambiente.
- **Lifecycle Policy**: objetos movidos para **S3 Glacier Instant Retrieval** após 90 dias, reduzindo custo de armazenamento para textos já processados.
- **SSE-S3** (Server-Side Encryption com chaves gerenciadas pela AWS) habilitada por padrão no bucket.
- **Bucket Policy** restritiva bloqueando acesso público e permitindo acesso apenas às roles IAM autorizadas.

### SQS + Lambda Event Source Mapping

Em desenvolvimento local, o `grade_worker` é um daemon que faz polling contínuo na fila SQS. Em produção, esse daemon seria substituído pelo mecanismo nativo **Lambda Event Source Mapping (ESM)**.

Com ESM, a própria AWS gerencia o polling da fila e invoca a Lambda automaticamente quando há mensagens disponíveis  eliminando a necessidade de manter um processo rodando continuamente.

Configurações recomendadas:
- **Batch size 1**: uma mensagem por invocação, simplificando o tratamento de erros (falha em uma mensagem não afeta outras)
- **Visibility Timeout 180s**: tempo suficiente para o Gemini processar a redação sem que a mensagem reapareça na fila prematuramente
- **maxReceiveCount 3**: após 3 tentativas de processamento com falha, a mensagem é movida automaticamente para a Dead Letter Queue
- **Dead Letter Queue (DLQ)**: fila SQS separada para mensagens que falharam repetidamente, permitindo inspeção manual e reprocessamento controlado

### RDS PostgreSQL

O banco de dados seria provisionado no **Amazon RDS PostgreSQL** com as seguintes configurações:

- **Multi-AZ**: réplica síncrona em outra Availability Zone para alta disponibilidade e failover automático
- **RDS Proxy**: componente crítico em arquiteturas serverless. Funções Lambda podem escalar para centenas de instâncias simultâneas em segundos, cada uma abrindo sua própria conexão com o banco. O PostgreSQL tem limite de conexões simultâneas, e esse padrão causa **connection exhaustion** rapidamente. O RDS Proxy mantém um pool de conexões persistentes com o banco e multiplexa as conexões das Lambdas sobre esse pool, resolvendo o problema sem alterações no código da aplicação.

### Transactional Outbox Pattern (consideração de produção)

#### O problema

No fluxo atual, a criação de uma submission envolve três operações sequenciais:

1. Upload para o S3
2. `INSERT` no PostgreSQL (status `PENDING`)
3. Publicação da mensagem no SQS

Essas três operações não são atômicas. Se a aplicação falhar entre o passo 2 e o passo 3 (por exemplo, um crash, timeout de rede ou exceção não tratada), a submission fica persistida no banco com status `PENDING` permanentemente, sem nunca ter sido enfileirada para correção. O estudante ficará esperando indefinidamente sem nenhuma resposta.

#### A solução: Transactional Outbox

O padrão **Transactional Outbox** resolve esse problema garantindo atomicidade entre a escrita no banco e o enfileiramento:

1. Em vez de publicar no SQS diretamente, a aplicação persiste dois registros na **mesma transação ACID**: o `Submission` (status `PENDING`) e um `OutboxEvent` (com o payload da mensagem SQS).
2. Um processo separado, o **relay worker**, faz polling periódico na tabela `outbox_events` usando `SELECT FOR UPDATE SKIP LOCKED` (lock otimista, seguro para múltiplas instâncias do relay).
3. O relay publica a mensagem no SQS e marca o `OutboxEvent` como processado.

Isso garante semântica **at-least-once**: se o relay falhar após publicar no SQS mas antes de marcar o evento como processado, ele republicará na próxima execução. Por isso, o consumer (grade_worker) deve ser **idempotente**  antes de processar, verifica se o status é diferente de `PENDING` (usando `SELECT FOR UPDATE`), descartando mensagens duplicadas.

#### Por que não está nesta implementação

Em um contexto de desenvolvimento local com LocalStack, a probabilidade de falha entre o DB insert e o SQS publish é negligenciável. O Transactional Outbox adiciona complexidade operacional significativa (nova tabela, novo processo, lógica de idempotência explícita) que não se justifica para o escopo deste exercício técnico. Em produção, com tráfego real e múltiplas instâncias, a implementação seria necessária.

## Escalabilidade e Observabilidade

### Escalabilidade

- **Lambda Concurrency Limit**: em produção, é importante configurar um limite de concorrência reservada para a Lambda do `grade_worker`. O Gemini tem limites de taxa (rate limits) por API key; sem limite de concorrência, um pico de mensagens na fila pode disparar centenas de invocações simultâneas e causar erros `429 Too Many Requests` no Gemini.
- **SQS como buffer natural**: a fila absorve picos de submissões sem pressionar o banco de dados ou o Gemini diretamente. O processamento ocorre na taxa que a Lambda consegue sustentar.
- **RDS Proxy**: conforme descrito acima, garante que o escalonamento horizontal das Lambdas não esgote as conexões do PostgreSQL.
- **Índice composto**: o índice `(student_id, created_at DESC)` garante que queries paginadas no endpoint de listagem sejam eficientes mesmo com milhões de registros, sem full table scan.

### Idempotência

O `grade_worker` utiliza `SELECT FOR UPDATE` ao atualizar o status de `PENDING` para `PROCESSING`. Isso garante que, caso a mesma mensagem seja entregue mais de uma vez pelo SQS (semântica at-least-once), apenas uma invocação processará a submission  as demais encontrarão o status diferente de `PENDING` e descartarão a mensagem sem reprocessar.

### Retries e DLQ

- **Visibility Timeout de 180s**: se o worker não deletar a mensagem dentro desse prazo (por timeout ou crash), a mensagem volta para a fila e pode ser reprocessada por outra instância.
- **maxReceiveCount 3**: após três reentregas sem sucesso, a mensagem é movida para a **Dead Letter Queue**, evitando que uma mensagem "venenosa" bloqueie o processamento indefinidamente.
- **DLQ para inspeção manual**: permite analisar a causa raiz de falhas persistentes e reprocessar as mensagens manualmente após correção.
- **Campo `status ERROR`**: complementa a DLQ  mesmo que a mensagem já tenha sido deletada da fila, é possível identificar submissions com falha diretamente no banco de dados via `WHERE status = 'ERROR'`.

### Logs e Métricas

- **CloudWatch Logs automático**: toda invocação de Lambda gera logs automaticamente no CloudWatch sem configuração adicional.
- **Structured logging JSON**: os logs da aplicação devem ser emitidos em formato JSON estruturado para facilitar queries no CloudWatch Logs Insights (exemplo: filtrar por `submission_id`, `student_id` ou `status`).
- **Métricas Lambda automáticas**: a AWS publica automaticamente no CloudWatch as seguintes métricas por função Lambda:
  - `Invocations`: total de invocações
  - `Errors`: invocações com erro
  - `Duration`: tempo de execução (p50, p95, p99)
  - `ConcurrentExecutions`: concorrência instantânea
  - `Throttles`: invocações bloqueadas por limite de concorrência

### Alertas Recomendados

| Alerta | Métrica | Threshold | Justificativa |
|---|---|---|---|
| Alta taxa de erro na Lambda | `Lambda Errors / Invocations` | > 5% | Indica falhas sistemáticas no processamento |
| Mensagens na DLQ | `SQS ApproximateNumberOfMessagesVisible` (DLQ) | > 0 | Qualquer mensagem na DLQ requer investigação |
| Erros 5xx na API | `API Gateway 5XXError` | > 0 | Erros internos na API em produção |
| Latência alta na API | `API Gateway IntegrationLatency p99` | > 2000ms | Degradação de experiência do usuário |
| Conexões RDS próximas do limite | `RDS DatabaseConnections` | > 80% do máximo | Risco iminente de connection exhaustion |
| Mensagens antigas na fila | `SQS ApproximateAgeOfOldestMessage` | > 5 minutos | Worker pode estar parado ou sobrecarregado |
