
+28
-0

import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from avatar import avatar_bp, init_app as init_avatar
from auth import auth_bp, init_app as init_auth

app = Flask(__name__)


allowed_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5177")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]

if not allowed_origins:
    allowed_origins = ["http://localhost:5177"]

if "*" in allowed_origins:
    cors_origins = "*"
else:
    cors_origins = allowed_origins

CORS(app, resources={
    r"/api/*": {
        "origins": cors_origins,
        "allow_headers": [
            "Content-Type",
            "Accept",
            "x-api-key",
            "X-User-Email",
            "X-Session-Id",
            "X-Refresh-Token",
        ],
    }
})

init_auth(app)
init_avatar(app)
app.register_blueprint(auth_bp)
app.register_blueprint(avatar_bp)

# Health check endpoint (required by App Runner)
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/')
def hello():
    return jsonify({"message": "Fitspace Backend API"})

# Simple GET endpoint for testing
@app.route('/api/users', methods=['GET'])
def test_get():
    return jsonify({
        "message": "GET request successful!",
        "method": "GET",
        "endpoint": "/api/users"
    }), 200

# POST endpoint for creating data
@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.get_json() or {}

    # Simple validation
    if not data.get('name'):
        return jsonify({"error": "Name is required"}), 400
    
    return jsonify({
        "message": "User created successfully!",
        "user": {
            "name": data.get('name'),
            "email": data.get('email', 'Not provided'),
            "id": 123  # Mock ID
        }
    }), 201

@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    response = {
        "error": exc.name,
        "message": exc.description or exc.name,
        "status": exc.code,
    }
    return jsonify(response), exc.code


@app.errorhandler(Exception)
def handle_uncaught_exception(exc: Exception):
    app.logger.exception("Unhandled exception: %s", exc)
    response = {
        "error": "Internal Server Error",
        "message": "Dogodila se neočekivana pogreška.",
        "status": 500,
    }
    return jsonify(response), 500


if __name__ == '__main__':
    # App Runner will call gunicorn, but this allows local testing
    app.run(host='0.0.0.0', port=8080, debug=True)