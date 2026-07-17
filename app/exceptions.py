class DatabaseConnectionError(Exception):
    """Raised when the application cannot reach the PostgreSQL database instance."""
    pass

class LogCreationError(Exception):
    """Raised when an insertion operation violates constraints or fails."""
    pass

class UserRegistrationError(Exception):
    """Raised when a user cannot be created, such as username conflict"""
    pass

class InvalidCredentialsError(Exception):
    """Raised when username or password parameters do not match records"""
    pass