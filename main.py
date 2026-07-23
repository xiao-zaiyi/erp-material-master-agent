import logging
import sys
from pathlib import Path

import uvicorn


def build_app():
    src_dir = str(Path(__file__).with_name("src"))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from web.api import create_app

    return create_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    uvicorn.run(build_app(), host="0.0.0.0", port=8000, reload=False)
