from flask import Flask, jsonify, request

from avatar import avatar_bp

app = Flask(__name__)
app.register_blueprint(avatar_bp)

# Health check endpoint (required by App Runner)
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/')
def hello():
    return jsonify({"message": "Hello from Flask on App Runner!"})

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

if __name__ == '__main__':
    # App Runner will call gunicorn, but this allows local testing
    app.run(host='0.0.0.0', port=8080, debug=True)