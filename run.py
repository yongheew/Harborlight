"""Launch from any current directory: python /path/to/harborlight/run.py."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("harborlight.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
