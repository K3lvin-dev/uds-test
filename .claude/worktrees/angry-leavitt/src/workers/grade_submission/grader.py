from google import genai

from src.infra.config import settings
from src.workers.grade_submission.schemas import GradingResult

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
        model="gemini-2.5-flash-lite",
        contents=_PROMPT_TEMPLATE.format(text=text),
        config={
            "response_mime_type": "application/json",
            "response_json_schema": GradingResult.model_json_schema(),
        },
    )
    if response.text is None:
        raise ValueError("Gemini returned empty response")
    return GradingResult.model_validate_json(response.text)
