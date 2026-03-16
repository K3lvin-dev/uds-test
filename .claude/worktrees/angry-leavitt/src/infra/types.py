from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import PlainSerializer

_BRT = ZoneInfo("America/Sao_Paulo")

BRTDatetime = Annotated[
    datetime,
    PlainSerializer(lambda dt: dt.astimezone(_BRT).isoformat(), return_type=str),
]
