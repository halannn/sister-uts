import uvicorn
from .app import create_app

# entrypoint
def main() -> None:
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8080,
        reload=False,
        workers=1,
    )

if __name__ == "__main__":
    main()
