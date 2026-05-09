import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3

table = boto3.resource("dynamodb").Table(os.environ["PAYMENTS_TABLE"])

ACCOUNTS = ["1001", "1002", "1003", "1004", "1005"]


def handler(event, context):
    """Inserts sample payments in SCHEDULED, PENDING, and PROCESSED states."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    items_written = 0

    with table.batch_writer() as batch:
        for i, account_id in enumerate(ACCOUNTS):
            # SCHEDULED payments for today and future dates
            for day_offset in range(0, 10):
                scheduled_time = (now + timedelta(days=day_offset)).strftime("%Y-%m-%dT09:00:00Z")
                payment_id = str(uuid.uuid4())
                batch.put_item(
                    Item={
                        "PK": f"a#{account_id}",
                        "SK": f"p#SCHEDULED#{scheduled_time}#{payment_id}",
                        "PaymentId": payment_id,
                        "AccountId": account_id,
                        "Status": "SCHEDULED",
                        "ScheduledTime": scheduled_time,
                        "DataBlob": f"payment-{account_id}-scheduled-{day_offset}",
                        "CreatedAt": now.isoformat(),
                    }
                )
                items_written += 1

            # PENDING payments for today
            for j in range(3):
                scheduled_time = f"{today}T10:{j:02d}:00Z"
                payment_id = str(uuid.uuid4())
                batch.put_item(
                    Item={
                        "PK": f"a#{account_id}",
                        "SK": f"p#PENDING#{scheduled_time}#{payment_id}",
                        "PaymentId": payment_id,
                        "AccountId": account_id,
                        "Status": "PENDING",
                        "ScheduledTime": scheduled_time,
                        "DataBlob": f"payment-{account_id}-pending-{j}",
                        "CreatedAt": now.isoformat(),
                    }
                )
                items_written += 1

            # PROCESSED payments from past days
            for day_offset in range(1, 6):
                scheduled_time = (now - timedelta(days=day_offset)).strftime("%Y-%m-%dT08:00:00Z")
                payment_id = str(uuid.uuid4())
                transaction_id = str(uuid.uuid4())
                batch.put_item(
                    Item={
                        "PK": f"a#{account_id}",
                        "SK": f"p#PROCESSED#{scheduled_time}#{payment_id}",
                        "PaymentId": payment_id,
                        "AccountId": account_id,
                        "Status": "PROCESSED",
                        "ScheduledTime": scheduled_time,
                        "TransactionId": transaction_id,
                        "DataBlob": f"payment-{account_id}-processed-{day_offset}",
                        "CreatedAt": (now - timedelta(days=day_offset)).isoformat(),
                        "ProcessedAt": (now - timedelta(days=day_offset, hours=-1)).isoformat(),
                    }
                )
                items_written += 1

    return {"statusCode": 200, "items_written": items_written}
