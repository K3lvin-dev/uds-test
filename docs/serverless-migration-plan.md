# Plano de Migração Serverless

> Documento de referência para evolução da arquitetura local (Docker Compose) para
> serverless na AWS. A implementação atual é a base — as mudanças de código são mínimas.

---

## Estado Atual

```
[Cliente]
    │
    ▼
[Docker: API Container]          FastAPI + uvicorn rodando continuamente
    │  grava atomicamente
    ▼
[Docker: Postgres]               submissions + outbox_events na mesma transação
    │
[Docker: Worker Container]       loop while True, polling outbox a cada 5s
    │  lê outbox_events
    ├──► [Docker: LocalStack S3]  upload do texto da redação
    ├──► [Docker: LocalStack SQS] publica submission_id
    └──► deleta outbox_event
```

---

## Arquitetura Alvo (Serverless — Opção B)

```
[Cliente]
    │
    ▼
[API Gateway HTTP API]
    │  dispara por requisição
    ▼
[Lambda: api]                    FastAPI + Mangum (handler de evento)
    │  grava atomicamente
    ▼
[Aurora Serverless v2]           submissions + outbox_events na mesma transação
    │                            (via RDS Proxy para gerenciar conexões)
    │
[EventBridge Scheduler]          rate(1 minute) — dispara o relay
    │
    ▼
[Lambda: outbox-relay]           _process_one() — 1 evento por invocação
    │  lê outbox_events
    ├──► [S3]                    upload do texto da redação
    ├──► [SQS]                   publica submission_id
    └──► deleta outbox_event
    │
[SQS: submissions-queue]
    │  Event Source Mapping
    ▼
[Lambda: grade-worker]           consome a fila, chama Gemini, atualiza DB
```

---

## O Que Muda no Código

### 1. Dependência nova: `mangum`

```toml
# pyproject.toml
dependencies = [
    ...
    "mangum>=0.19.0",
]
```

### 2. `src/main.py` — expor handler Lambda

```python
# adicionar ao final do arquivo
from mangum import Mangum
lambda_handler = Mangum(app)
```

O `app` FastAPI não muda nada. O `lambda_handler` é o entry point da Lambda da API.

### 3. `src/workers/outbox_relay/relay.py` — expor handler Lambda

```python
# adicionar ao final do arquivo
def lambda_handler(event, context):
    """Entry point para EventBridge Scheduler."""
    import asyncio
    asyncio.run(_process_one())
```

A função `_process_one()` já existe e já está no formato correto.
O `while True` e o `_relay_loop` não são usados na Lambda — o EventBridge faz o loop.

### 4. `src/workers/grade_submission/consumer.py` — handler Lambda para SQS

```python
# novo arquivo — Lambda acionada pelo SQS Event Source Mapping
import asyncio
import json

from src.workers.grade_submission.handler import process


def lambda_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        asyncio.run(process({"Body": record["body"]}))
```

O `process()` do handler existente não muda.

### 5. `src/infra/config.py` — sem mudança

`pydantic-settings` já lê de variáveis de ambiente, que na Lambda são configuradas
no próprio serviço. Nenhuma alteração necessária.

### 6. `src/infra/database.py` — ajuste de pool para Lambda

```python
# Lambda tem conexões efêmeras — pool pequeno evita esgotamento no Aurora
engine = create_async_engine(
    settings.database_url,
    pool_size=2,
    max_overflow=0,
    echo=False,
)
```

Com **RDS Proxy** na frente do Aurora, o pool pode ser ainda menor (1).

---

## Infraestrutura (SAM Template)

Criar `template.yaml` na raiz do projeto:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Runtime: python3.13
    Timeout: 30
    Environment:
      Variables:
        DATABASE_URL: !Ref DatabaseUrl
        AWS_DEFAULT_REGION: us-east-1
        S3_BUCKET: submissions-bucket
        SQS_QUEUE_URL: !Ref SubmissionsQueue
        GEMINI_API_KEY: !Ref GeminiApiKey

Resources:

  ApiFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src.main.lambda_handler
      Events:
        ApiGateway:
          Type: HttpApi
          Properties:
            Path: /{proxy+}
            Method: ANY

  OutboxRelayFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src.workers.outbox_relay.relay.lambda_handler
      Timeout: 60
      Events:
        Schedule:
          Type: ScheduleV2
          Properties:
            ScheduleExpression: rate(1 minute)

  GradeWorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src.workers.grade_submission.consumer.lambda_handler
      Timeout: 120
      Events:
        SQSTrigger:
          Type: SQS
          Properties:
            Queue: !GetAtt SubmissionsQueue.Arn
            BatchSize: 1

  SubmissionsQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 120
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt SubmissionsDLQ.Arn
        maxReceiveCount: 3

  SubmissionsDLQ:
    Type: AWS::SQS::Queue
```

---

## Checklist de Migração

### Fase 1 — Preparação do código (baixo risco)

- [ ] Adicionar `mangum` às dependências
- [ ] Expor `lambda_handler = Mangum(app)` em `src/main.py`
- [ ] Expor `lambda_handler` em `src/workers/outbox_relay/relay.py`
- [ ] Criar `src/workers/grade_submission/consumer.py` com handler SQS
- [ ] Ajustar `pool_size` do engine para ambiente Lambda
- [ ] Testar localmente com `sam local start-api` e `sam local invoke`

### Fase 2 — Infraestrutura AWS

- [ ] Criar Aurora Serverless v2 (PostgreSQL 17 compatível)
- [ ] Criar RDS Proxy apontando para o Aurora
- [ ] Criar bucket S3 `submissions-bucket`
- [ ] Criar fila SQS `submissions-queue` com DLQ configurada
- [ ] Rodar `schema.sql` no Aurora via migration script
- [ ] Configurar secrets (GEMINI_API_KEY, DATABASE_URL) no AWS Secrets Manager

### Fase 3 — Deploy

- [ ] `sam build`
- [ ] `sam deploy --guided`
- [ ] Verificar API Gateway endpoint funcionando
- [ ] Verificar EventBridge Schedule criado (rate 1 minute)
- [ ] Verificar SQS Event Source Mapping na GradeWorkerFunction
- [ ] Smoke test end-to-end

### Fase 4 — Observabilidade

- [ ] Habilitar CloudWatch Logs em todas as Lambdas
- [ ] Criar alarme CloudWatch para mensagens na DLQ > 0
- [ ] Criar alarme para erros Lambda acima de threshold
- [ ] Configurar X-Ray tracing nas Lambdas críticas

---

## Limitações Conhecidas e Trade-offs

| Limitação | Impacto | Mitigação |
|---|---|---|
| Latência do outbox até 1 min | Submissão demora até 1 min para ir ao S3/SQS | Aceitável para correção de redações |
| Cold start Lambda | ~500ms na primeira requisição | Provisioned Concurrency na API Lambda |
| Aurora Serverless cold start | ~20s se ficar idle | Manter mínimo de 1 ACU ativo |
| Conexões Lambda → Aurora | Esgotamento sob alta concorrência | RDS Proxy obrigatório |
| EventBridge Schedule mínimo 1 min | Não serve para casos real-time | Trocar para DynamoDB Streams se necessário |

---

## Comparação com Opção A (DynamoDB Streams)

Se a latência de 1 minuto se tornar um problema no futuro, a evolução natural é:

| | Opção B (atual — Scheduler) | Opção A (futura — DynamoDB) |
|---|---|---|
| Latência do outbox | até 1 min | segundos |
| Banco principal | Aurora PostgreSQL | Aurora PostgreSQL |
| Tabela outbox | `outbox_events` no Postgres | Tabela DynamoDB separada |
| Trigger do relay | EventBridge Scheduler | DynamoDB Streams → EventBridge Pipes |
| Mudança de código | mínima | média (novo client DynamoDB para outbox) |
| Custo adicional | baixo | baixo (DynamoDB on-demand) |

A migração de B para A no futuro seria:
1. Criar tabela DynamoDB `outbox_events`
2. Trocar `db.add(outbox_event)` no handler por `dynamodb.put_item()`
3. Criar EventBridge Pipe: DynamoDB Stream → SQS
4. Remover a Lambda `outbox-relay` e o Schedule

---

## Resumo

O código atual já está ~90% pronto para serverless. As mudanças são:

- **2 linhas** para expor a API como Lambda (`Mangum`)
- **1 função** para expor o relay como Lambda handler
- **1 arquivo novo** para o consumer SQS do grade worker
- **1 ajuste** de pool de conexões

O `while True` some — o EventBridge assume esse papel.
O `docker-compose.yml` permanece para desenvolvimento local.
