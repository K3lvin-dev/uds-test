# Submissions Service

Micro-serviço REST para registro e correção automática de redações com IA (Google Gemini Flash).

## Stack

- **Python 3.13** + **uv** (gerenciador de pacotes e ambiente virtual)
- **FastAPI 0.135** — 3 endpoints REST com validação Pydantic
- **SQLAlchemy 2.0 (async) + asyncpg** — acesso assíncrono ao PostgreSQL
- **PostgreSQL 17** — persistência principal (submissions + outbox_events)
- **LocalStack 4.0** — emulação local de S3 e SQS
- **boto3** — upload/download S3 e publish/consume SQS
- **Google Gemini 2.5 Flash Lite** (`google-genai`) — correção via IA com saída JSON estruturada
- **Transactional Outbox Pattern** — garante consistência entre DB e mensageria sem 2PC
- **Arquitetura:** Vertical Slice Architecture (VSA)

## Como funciona

O fluxo de uma submissão percorre as seguintes etapas:

1. **POST /api/v1/submissions/** — a API recebe a redação, cria um registro `Submission` (status `PENDING`) e um `OutboxEvent` na mesma transação do banco. Nenhuma chamada externa é feita neste momento.
2. **Outbox Relay Worker** — poll no banco busca eventos pendentes na tabela `outbox_events`. Para cada evento, faz upload do texto no S3 e publica o `submission_id` na fila SQS, depois remove o evento da tabela.
3. **Grade Worker** — consome mensagens do SQS, baixa o texto do S3, chama o Gemini para correção estruturada e atualiza a submission com nota, critérios e feedback (status `GRADED`).
4. **Retry automático** — submissões com status `ERROR` e `retry_count < 3` são automaticamente recolocadas na fila após 5 minutos pelo Outbox Relay.

## Pré-requisitos

- Docker e Docker Compose
- Python 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Chave de API do Gemini — [aistudio.google.com](https://aistudio.google.com/app/apikey)

## Rodando Localmente

### 1. Clone e configure o ambiente

```bash
git clone <repo-url>
cd uds-test

cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY com sua chave
```

### 2. Suba a infraestrutura e os workers

```bash
docker compose up -d
# Aguarde os containers ficarem healthy (~15-20s)
docker compose ps
```

Os containers `submissions_postgres`, `submissions_localstack`, `submissions_outbox_relay` e `submissions_grade_worker` devem aparecer como `healthy` / `running`.

### 3. Instale as dependências Python

```bash
uv sync
```

### 4. Inicie a API

```bash
uv run start
```

API disponível em: `http://localhost:8000`
Documentação interativa: `http://localhost:8000/docs`

### 5. Verifique o health check

```bash
curl http://localhost:8000/health
# {"status":"healthy"}
```

## Endpoints

### POST /api/v1/submissions/

Registra uma nova redação para correção.

```bash
curl -s -X POST http://localhost:8000/api/v1/submissions/ \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "aluno-001",
    "text": "A tecnologia tem transformado a sociedade de maneira profunda e irreversível..."
  }' | python3 -m json.tool
```

Resposta `201 Created`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "status": "PENDING",
  "created_at": "2026-03-15T10:00:00Z"
}
```

O header `Location` aponta para o endpoint de consulta: `Location: /api/v1/submissions/<id>`

---

### GET /api/v1/submissions/{id}

Retorna os detalhes de uma submissão, incluindo nota e critérios após a correção.

```bash
curl -s http://localhost:8000/api/v1/submissions/550e8400-e29b-41d4-a716-446655440000 \
  | python3 -m json.tool
```

Resposta `200 OK` (após correção):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "student_id": "aluno-001",
  "s3_key": "submissions/550e8400-e29b-41d4-a716-446655440000.txt",
  "status": "GRADED",
  "score": "8.50",
  "criteria": {
    "grammar":        { "score": 9.0, "feedback": "Excelente gramática." },
    "coherence":      { "score": 8.0, "feedback": "Boa coesão textual." },
    "argumentation":  { "score": 7.5, "feedback": "Argumentos sólidos." },
    "vocabulary":     { "score": 9.5, "feedback": "Vocabulário rico." }
  },
  "overall_feedback": "Redação de alta qualidade com argumentação bem estruturada.",
  "created_at": "2026-03-15T10:00:00Z",
  "updated_at": "2026-03-15T10:00:05Z"
}
```

Retorna `404 Not Found` se o ID não existir.

---

### GET /api/v1/submissions/?student_id=aluno-001

Lista submissões de um aluno com paginação (ordenadas por data decrescente).

```bash
curl -s "http://localhost:8000/api/v1/submissions/?student_id=aluno-001&page=1&per_page=10" \
  | python3 -m json.tool
```

Resposta `200 OK`:
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "student_id": "aluno-001",
      "status": "GRADED",
      "score": "8.50",
      "created_at": "2026-03-15T10:00:00Z",
      "updated_at": "2026-03-15T10:00:05Z"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10
}
```

**Parâmetros de query:**
| Parâmetro  | Tipo   | Padrão | Descrição              |
|------------|--------|--------|------------------------|
| student_id | string | —      | ID do aluno (obrigatório) |
| page       | int    | 1      | Página (mínimo: 1)     |
| per_page   | int    | 10     | Itens por página (1-100) |

## Arquitetura na AWS

Em produção, este serviço seria implantado com componentes AWS nativos mantendo a mesma lógica de negócio:

**API Gateway + Lambda:** Os 3 endpoints REST seriam expostos via API Gateway, cada um acionando um Lambda Python separado (create, get, list). O handler seria adaptado para o formato de evento do API Gateway usando `Mangum`. A separação por função permite escalonamento e permissões IAM independentes. O código Python permanece idêntico — apenas o entry point muda.

**S3:** O bucket S3 armazena os textos das redações exatamente como no ambiente local. As permissões são gerenciadas via IAM Role associada ao Lambda, sem credenciais hardcoded. O mesmo padrão de chave `submissions/{uuid}.txt` é mantido.

**SQS + Lambda Event Source Mapping:** A fila SQS desacopla criação e correção. O Lambda de criação publica uma mensagem com o `submission_id`. Um Lambda de worker é acionado automaticamente pelo SQS Event Source Mapping (em substituição ao consumer daemon local), processando uma mensagem por invocação. A fila possui DLQ (Dead Letter Queue) configurada para 3 tentativas — substituindo o mecanismo de retry automático implementado no Outbox Relay Worker.

**Outbox Relay — EventBridge Scheduler + Lambda:** O padrão Transactional Outbox é mantido. O daemon de polling local é substituído por um EventBridge Scheduler que aciona um Lambda a cada minuto para processar eventos pendentes na tabela `outbox_events`. Essa abordagem preserva a atomicidade DB+mensageria sem necessidade de daemon persistente, sendo a solução natural para ambiente serverless com PostgreSQL.

**RDS PostgreSQL:** O banco seria o Amazon RDS for PostgreSQL (Multi-AZ para alta disponibilidade). A conexão usa RDS Proxy para gerenciar o pool de conexões e evitar esgotamento em ambiente serverless, onde cada invocação Lambda pode abrir novas conexões.

## Escalabilidade e Observabilidade

**Escalabilidade:** Lambda escala automaticamente até 1.000 execuções concorrentes por região (ajustável). O SQS suporta throughput virtualmente ilimitado. O RDS Proxy gerencia o pool de conexões, evitando sobrecarga no banco durante picos. O `SELECT FOR UPDATE SKIP LOCKED` no Outbox Relay garante processamento seguro com múltiplas instâncias concorrentes.

**Idempotência:** O Grade Worker verifica o status antes de processar (`status != "PENDING"` → ignora). Isso protege contra reentregas do SQS sem efeitos colaterais.

**Retry e DLQ:** O SQS possui `VisibilityTimeout` de 120s (suficiente para a chamada ao Gemini). Após 3 falhas consecutivas, a mensagem vai para a DLQ para inspeção manual. O Outbox Relay implementa retry automático para submissions com status `ERROR` (até 3 tentativas com intervalo mínimo de 5 minutos).

**Logs e Alertas:** CloudWatch Logs recebe automaticamente todos os logs das funções Lambda. CloudWatch Alarms podem ser configurados para: taxa de erro Lambda acima do threshold, mensagens na DLQ, latência do API Gateway e conexões do RDS próximas ao limite.
