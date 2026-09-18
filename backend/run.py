import sys
from pathlib import Path
import uvicorn

# Ensure the backend directory is in the Python module search path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import HOST, PORT

def main():
    print(f"Starting Multimodal EHR RAG Assistant Backend on http://{HOST}:{PORT} (reload=True)...")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=True,
        reload_dirs=[str(BACKEND_DIR / "app")]
    )

if __name__ == "__main__":
    main()
