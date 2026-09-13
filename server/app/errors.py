class ApiError(Exception):
    """openapi.yaml의 ErrorResponse 봉투({"error": {code, message, details}})로 변환되는 예외."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
