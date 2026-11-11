"""Typed errors. Each one has a clean message and a CLI exit code."""


class ScannerError(Exception):
    exit_code = 1


class InvalidRepoURLError(ScannerError):
    exit_code = 2


class RepositoryNotFoundError(ScannerError):
    exit_code = 3


class RateLimitError(ScannerError):
    exit_code = 4

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AuthError(ScannerError):
    exit_code = 5


class GitHubUnavailableError(ScannerError):
    exit_code = 6


class SummarizerError(ScannerError):
    exit_code = 7


class ConfigError(ScannerError):
    exit_code = 8


class EmptyRepoError(ScannerError):
    exit_code = 9
