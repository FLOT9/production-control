from typing import Protocol

from src.application.dto.batch_import import BatchCsvParseResult


class BatchParser(Protocol):
    def parse(self, data: bytes) -> BatchCsvParseResult: ...
