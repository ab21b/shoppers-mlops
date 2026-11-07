from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MONTHS = Literal["Feb", "Mar", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]  # ровно как в датасете
VISITORS = Literal["New_Visitor", "Returning_Visitor", "Other"]


class Features(BaseModel):

    model_config = ConfigDict(extra="forbid")

    Administrative: int = Field(ge=0, le=100, description="Число просмотренных страниц аккаунта")
    Administrative_Duration: float = Field(ge=0, le=100_000, description="Секунд на этих страницах")
    Informational: int = Field(ge=0, le=100, description="Число информационных страниц")
    Informational_Duration: float = Field(ge=0, le=100_000)
    ProductRelated: int = Field(ge=0, le=5000, description="Число страниц товаров")
    ProductRelated_Duration: float = Field(ge=0, le=500_000)
    BounceRates: float = Field(ge=0, le=1, description="Доля отказов")
    ExitRates: float = Field(ge=0, le=1, description="Доля выходов")
    PageValues: float = Field(ge=0, le=10_000, description="Средняя ценность страниц перед покупкой")
    SpecialDay: float = Field(ge=0, le=1, description="Близость к празднику")
    Month: MONTHS
    OperatingSystems: int = Field(ge=1, le=8)
    Browser: int = Field(ge=1, le=13)
    Region: int = Field(ge=1, le=9)
    TrafficType: int = Field(ge=1, le=20)
    VisitorType: VISITORS
    Weekend: bool


class Prediction(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    score: float = Field(description="Вероятность покупки, 0..1")
    purchase: bool = Field(description="score >= порог из паспорта модели")
    model_version: str
    request_id: str
    latency_ms: float
