class TdxError(Exception):
    """Base exception for the embedded TDX protocol client."""


class TdxConnectionError(TdxError):
    """Connection, timeout, or framing failure."""


class TdxDecodeError(TdxError):
    """Malformed or truncated TDX response."""
