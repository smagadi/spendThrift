class SpendError(Exception):
    """Domain error for the Python API."""


class CardExistsError(SpendError):
    pass


class CardNotFoundError(SpendError):
    pass


class InactiveCardError(SpendError):
    pass


class DuplicateStatementError(SpendError):
    def __init__(self, message: str, uploaded_at=None):
        super().__init__(message)
        self.uploaded_at = uploaded_at


class CategoryError(SpendError):
    pass


class BackupError(SpendError):
    pass


class ParseError(SpendError):
    pass
