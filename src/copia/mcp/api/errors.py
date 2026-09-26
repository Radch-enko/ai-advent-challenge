from fastapi import status

MCP_ERROR_STATUS_CODES = {
    "mcp_endpoint_rejected": 422,
    "mcp_header_rejected": 422,
    "mcp_auth_required": status.HTTP_401_UNAUTHORIZED,
    "mcp_access_denied": status.HTTP_403_FORBIDDEN,
    "mcp_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "mcp_redirect_rejected": status.HTTP_502_BAD_GATEWAY,
    "mcp_connection_failed": status.HTTP_502_BAD_GATEWAY,
    "mcp_response_too_large": status.HTTP_502_BAD_GATEWAY,
    "mcp_protocol_error": status.HTTP_502_BAD_GATEWAY,
}
