from typing import Any, Literal, TypedDict

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)

Symbol = Literal["BTCUSDT", "ETHUSDT", "BNBUSDT"]
Period = Literal["24h", "7d"]


class Model(BaseModel):
    # 클래스에 추가 필드 거부·엄격한 타입 검사·빈 문자열 거부를 적용
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        str_min_length=1,
    )


class ResearchPlan(Model):
    action: Literal["research", "clarify", "unsupported"]
    symbols: list[Symbol] = Field(default_factory=list)
    period: Period | None = None
    document_query: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "ResearchPlan":
        """Check that research fields agree with the selected action.

        Args:
            self: Research plan after individual field validation.

        Returns:
            The validated research plan.
        """
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("symbols must not contain duplicates")

        if self.action == "research":
            if self.symbols and self.period is None:
                raise ValueError("market research requires a period")
            if not self.symbols and self.period is not None:
                raise ValueError("a period requires at least one symbol")
            if not self.symbols and self.document_query is None:
                raise ValueError("research requires market symbols or a document query")
            if self.message is not None:
                raise ValueError("research must not include a clarification message")

        else:
            if (
                self.symbols
                or self.period is not None
                or self.document_query is not None
            ):
                raise ValueError(
                    "clarify and unsupported must not include research fields"
                )

            if self.message is None:
                raise ValueError("clarify and unsupported require a message")

        return self


class Source(Model):
    source_id: str
    kind: Literal["market", "document"]
    title: str
    url: HttpUrl
    content: str
    retrieved_at: AwareDatetime


class DraftAnswer(Model):
    answer: str
    source_ids: list[str] = Field(default_factory=list)


class Reflection(Model):
    needs_more_research: bool
    reason: str
    follow_up_query: str | None = None

    @model_validator(mode="after")
    def validate_follow_up_query(self) -> "Reflection":
        """Check that the follow-up query agrees with the research decision.

        Args:
            self: Reflection after individual field validation.

        Returns:
            The validated reflection.
        """
        if self.needs_more_research:
            if self.follow_up_query is None:
                raise ValueError("additional research requires a follow-up query")
        elif self.follow_up_query is not None:
            raise ValueError("a follow-up query requires additional research")

        return self


class ResearchResult(Model):
    status: Literal[
        "completed",
        "partial",
        "insufficient_evidence",
        "needs_clarification",
        "unsupported",
        "error",
    ]
    answer: str
    sources: list[Source] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sources(self) -> "ResearchResult":
        """Check source uniqueness and citation references.

        Args:
            self: Research result after individual field validation.

        Returns:
            The validated result.
        """
        available_ids = [source.source_id for source in self.sources]
        available_ids_set = set(available_ids)
        cited_id_set = set(self.source_ids)

        if len(available_ids) != len(available_ids_set):
            raise ValueError("sources must have unique source IDs")

        if len(self.source_ids) != len(cited_id_set):
            raise ValueError("source_ids must not contain duplicates")

        if not cited_id_set.issubset(available_ids_set):
            raise ValueError("every cited source ID must exist in sources")

        if self.status in {"completed", "partial"} and not self.source_ids:
            raise ValueError("completed and partial results require at least one cited source")

        return self


class ResearchState(TypedDict, total=False):
    question: str
    plan: ResearchPlan
    sources: list[Source]
    draft: DraftAnswer
    reflection: Reflection
    research_round: int
    llm_responses: list[dict[str, Any]]
    error: str
    result: ResearchResult
