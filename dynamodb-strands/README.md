# Banking Scheduled Payments - DynamoDB Design Challenge

Implementación del desafío de diseño de DynamoDB del [Amazon DynamoDB Immersion Day](https://catalog.workshops.aws/dynamodb-labs/en-US): un backend de pagos bancarios programados que modela los access patterns usando Single Table Design.

Basado en el artículo [DynamoDB Design Challenges](https://builder.aws.com/content/39CzCb5zKsaWxDnWQoMLulQpYPO/dynamodb-design-challenges).

## Arquitectura

```
┌─────────────────┐         ┌─────────────────────────────────┐
│  AWS Lambda     │         │  DynamoDB Table                 │
│  seed-data      │────────▶│  PK: a#{AccountID}              │
│                 │  writes  │  SK: p#{Status}#{Time}#{PayID}  │
└─────────────────┘         │                                 │
                            │  GSI: StatusIndex               │
                            │    PK: Status                   │
                            │    SK: ScheduledTime            │
                            └─────────────────────────────────┘
```

## Tabla DynamoDB

### Diseño de claves

| Atributo | Formato | Ejemplo |
|----------|---------|---------|
| PK (Partition Key) | `a#{ACCOUNT_ID}` | `a#1001` |
| SK (Sort Key) | `p#{STATUS}#{ISO_8601}#{PAYMENT_ID}` | `p#SCHEDULED#2026-02-05T09:00:00Z#uuid` |

### Global Secondary Index (StatusIndex)

| Atributo | Formato | Ejemplo |
|----------|---------|---------|
| GSI-PK | `Status` | `SCHEDULED` |
| GSI-SK | `ScheduledTime` | `2026-02-05T09:00:00Z` |

Este GSI permite consultar pagos por estado a través de todas las cuentas. Por ejemplo, obtener todos los pagos `SCHEDULED` para una fecha específica sin importar la cuenta.

### Atributos del item

| Campo | Tipo | Descripción |
|-------|------|-------------|
| PK | String | Partition key de la tabla |
| SK | String | Sort key de la tabla |
| PaymentId | String | UUID único del pago |
| AccountId | String | ID de la cuenta bancaria |
| Status | String | `SCHEDULED`, `PENDING` o `PROCESSED` |
| ScheduledTime | String | Fecha/hora programada (ISO 8601) |
| DataBlob | String | Datos del pago (max 8 KB total por item) |
| TransactionId | String | ID de transacción (solo en estado PROCESSED) |
| CreatedAt | String | Timestamp de creación |
| ProcessedAt | String | Timestamp de procesamiento (solo en PROCESSED) |

### Access patterns soportados

| Pattern | Query |
|---------|-------|
| Pagos de una cuenta por estado | `PK = a#1001` y `SK begins_with p#SCHEDULED` |
| Pagos de una cuenta en un rango de fechas | `PK = a#1001` y `SK BETWEEN p#SCHEDULED#2026-02-01 AND p#SCHEDULED#2026-03-01` |
| Pagos de todas las cuentas por estado y fecha (GSI) | `Status = SCHEDULED` y `ScheduledTime begins_with 2026-02-05` |
| Pagos pendientes de hoy (GSI) | `Status = PENDING` y `ScheduledTime begins_with 2026-02-05` |

## Lambda: seed-data

Función que inserta datos de ejemplo en la tabla para demostrar los access patterns. Genera **90 items** distribuidos en 5 cuentas (`1001`-`1005`):

| Estado | Items por cuenta | Total | Descripción |
|--------|-----------------|-------|-------------|
| SCHEDULED | 10 | 50 | Pagos programados para hoy y los próximos 9 días |
| PENDING | 3 | 15 | Pagos del día en proceso de transacción |
| PROCESSED | 5 | 25 | Pagos completados de los últimos 5 días (incluyen TransactionId) |

## Despliegue

### Prerrequisitos

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.13
- Credenciales de AWS configuradas

### Build y deploy

```bash
sam build
sam deploy --guided
```

Durante el `--guided`, se te pedirá un nombre de stack (por ejemplo `banking-payments`). La tabla se creará como `{stack-name}-payments`.

## Invocar la Lambda

### Desde la CLI de AWS

```bash
aws lambda invoke \
  --function-name {stack-name}-seed-data \
  --payload '{}' \
  response.json

cat response.json
```

### Desde SAM CLI (local)

```bash
sam local invoke SeedDataFunction --event events/empty.json
```

Para esto, crea el archivo `events/empty.json`:

```json
{}
```

### Desde SAM CLI (remoto)

```bash
sam remote invoke SeedDataFunction --stack-name {stack-name}
```

### Respuesta esperada

```json
{
  "statusCode": 200,
  "items_written": 90
}
```

## Verificar los datos

Después de invocar la Lambda, puedes consultar la tabla:

```bash
# Pagos SCHEDULED de la cuenta 1001
aws dynamodb query \
  --table-name {stack-name}-payments \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk":{"S":"a#1001"}, ":sk":{"S":"p#SCHEDULED"}}'

# Todos los pagos PENDING de hoy usando el GSI
aws dynamodb query \
  --table-name {stack-name}-payments \
  --index-name StatusIndex \
  --key-condition-expression "#s = :status AND begins_with(ScheduledTime, :today)" \
  --expression-attribute-names '{"#s":"Status"}' \
  --expression-attribute-values '{":status":{"S":"PENDING"}, ":today":{"S":"2026-05-09"}}'
```

## Cleanup

```bash
sam delete --stack-name {stack-name}
```
