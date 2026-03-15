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

    await s3.upload_text(s3_key, request.text)

    submission = Submission(
        id=submission_id,
        student_id=request.student_id,
        s3_key=s3_key,
        status="PENDING",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    try:
        await sqs.publish_message(str(submission_id))
    except Exception as exc:
        # Submission já foi commitada. Loga o erro mas retorna sucesso ao cliente —
        # a mensagem pode ser reenfileirada manualmente ou via retry. Para produção,
        # considerar transactional outbox para garantir entrega.
        print(f"[create_submission] WARNING: falha ao publicar SQS para {submission_id}: {exc}")

    return CreateSubmissionResponse.model_validate(submission)
