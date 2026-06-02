"""
Found IT — Entry Point

Start the application:
    python run.py

This serves both the Flask REST API and the static frontend.
"""

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
