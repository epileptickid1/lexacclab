from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Span:
    """One-based source coordinates. The end is exclusive."""

    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True)
class Node:
    kind: str
    span: Span
    value: str | int | None = None
    children: tuple[Node, ...] = ()

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {"kind": self.kind}
        if self.value is not None:
            record["value"] = self.value
        record["span"] = asdict(self.span)
        record["children"] = [child.to_dict() for child in self.children]
        return record


class Diagnostic(Exception):
    def __init__(self, stage: str, message: str, span: Span):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.span = span
