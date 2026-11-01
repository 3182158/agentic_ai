"""Run the server: python -m ticket_leave_mcp"""

import uvicorn

from .config import get_settings
from .server import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
