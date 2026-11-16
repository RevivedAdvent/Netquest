"""Development entry point. Binds to localhost only."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    cfg = app.config
    print(f"NetQuest running at http://{cfg['HOST']}:{cfg['PORT']}  (local only)")
    app.run(host=cfg["HOST"], port=cfg["PORT"], debug=cfg["DEBUG"])
