from ..exc import BaseWarning, BaseError


class RPCWarning(BaseWarning, code="rpc"):
    """Base class or RPC warnings"""


class RPCDeprecatedVersion(RPCWarning, code="deprecated"):
    """API version is deprecated"""

    message: str = "API version is deprecated"


class RPCError(BaseError, code="rpc"):
    """Base class or RPC errors"""


class RPCParseError(RPCError, code="parse"):
    """Server cannot parse request body"""

    message: str = "Parse error"


class RPCInvalidRequest(RPCError, code="invalid_request"):
    """Server received invalid request object"""

    message: str = "Invalid request"


class RPCUnsupportedVersion(RPCError, code="unsupported_version"):
    """Requested API version is not provided by server"""

    message: str = "Unsupported API version"


class RPCUndefinedMethod(RPCError, code="undefined_method"):
    """Requested method is not provided by API"""

    message: str = "Undefined method"


class RPCInvalidParams(RPCError, code="invalid_params"):
    """Requested method does not accept passed parameters"""

    message: str = "Invalid parameters"


class RPCInternalError(RPCError, code="internal"):
    """Internal server error"""

    message: str = "Internal server error"
