"""NetQuest application factory.

Run with:  python run.py     (binds to 127.0.0.1 only)

Design notes
------------
* No shell execution of any kind. The backend never runs commands; the learner
  pastes output from their own terminal into the app.
* Everything is local: content JSON + SQLite. No outbound network calls.
"""
from __future__ import annotations

from flask import Flask, render_template

from config import Config
from database import close_db, init_db


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, instance_path=str(config_object.INSTANCE_DIR))
    app.config.from_object(config_object)

    app.teardown_appcontext(close_db)
    init_db(app)

    from routes.api import bp as api_bp
    from routes.case_studies import bp as missions_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.interview import bp as interview_bp
    from routes.labs import bp as labs_bp
    from routes.learning import bp as learning_bp
    from routes.progress import bp as progress_bp
    from routes.settings import bp as settings_bp
    from routes.simulations import bp as simulations_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(labs_bp)
    app.register_blueprint(simulations_bp)
    app.register_blueprint(missions_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(settings_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404,
                               message="That page does not exist."), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500,
                               message="Internal error. Check the terminal output."), 500

    @app.context_processor
    def inject_globals():
        from services import progress_service

        return {
            "days_remaining": progress_service.days_remaining(),
            "rank_info": progress_service.rank_progress(),
            "accelerated": progress_service.accelerated_mode(),
        }

    @app.template_filter("mins")
    def mins(value):
        return f"{value} min"

    return app


app = create_app()
