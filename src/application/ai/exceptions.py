class AssistantNotConfiguredError(Exception):
    def __init__(self) -> None:
        super().__init__("Ассистент не настроен")


class LLMUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Модель временно недоступна")


class AssistantTimeoutError(Exception):
    def __init__(self) -> None:
        super().__init__("Истекло время обработки вопроса")


class InvalidModelResponseError(Exception):
    def __init__(self) -> None:
        super().__init__("Модель вернула некорректный запрос инструмента")


class InvalidToolResultError(Exception):
    def __init__(self) -> None:
        super().__init__("Не удалось получить проверенную статистику")


class AssistantDataUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Источник данных ассистента временно недоступен")
