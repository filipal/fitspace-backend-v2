# FitSpace Backend API

A Flask-based REST API for managing user avatars with comprehensive measurement data, morph targets, and quick mode settings. The application provides a complete avatar configuration system with PostgreSQL persistence and JWT-based authentication.

## 🚀 Live Deployment

- **Production URL**: https://tea9as8upn.eu-central-1.awsapprunner.com
- **Health Check**: https://tea9as8upn.eu-central-1.awsapprunner.com/health
- **Auto-Deploy**: ✅ Enabled on `main` branch
- **Deployment Dashboard**: [AWS App Runner Console](https://eu-central-1.console.aws.amazon.com/apprunner/home?region=eu-central-1#/services/dashboard?service_arn=arn%3Aaws%3Aapprunner%3Aeu-central-1%3A027728694574%3Aservice%2Fpixel-streaming-backend%2F8fe42d5834d644b5ba150b7ae4b5a93b&active_tab=logs)

## 📋 Features

### Avatar Management
- **CRUD Operations**: Create, read, update, and delete user avatars
- **Measurement System**: Support for basic and body measurements
- **Morph Targets**: Advanced morphological customization with slider and Unreal Engine values
- **Quick Mode Settings**: Simplified avatar configuration with body shape and athletic level presets
- **User Quota**: Maximum 5 avatars per user with automatic slot management

### Authentication & Authorization
- **JWT-based Authentication**: Secure token-based user authentication
- **Session Management**: Support for session IDs and refresh tokens
- **User Context**: Email and session tracking for enhanced user management
- **API Key Protection**: Optional API key validation for token generation

### Data Management
- **PostgreSQL Integration**: Robust relational database with proper constraints
- **Transaction Safety**: ACID-compliant operations with automatic rollback
- **Measurement Validation**: Type-safe numeric measurement handling
- **Duplicate Prevention**: Unique avatar names per user

## 🏗️ Architecture

```
├── app.py                 # Flask application entry point
├── auth/                  # Authentication module
│   └── __init__.py        # JWT handling, token management
├── avatar/                # Avatar management module
│   ├── routes.py          # REST API endpoints
│   └── repository.py      # PostgreSQL data layer
├── db/
│   └── schema.sql         # Database schema definition
└── tests/
    └── test_avatar_routes.py  # Comprehensive test suite
```

## 🛠️ Local Development Setup

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Git

### 1. Clone Repository
```bash
git clone https://github.com/e-kipica/fitspace-backend.git
cd fitspace-backend
```

### 2. Environment Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Configuration
```bash
# Set your database URL
export DATABASE_URL="postgresql://username:password@localhost:5432/fitspace"

# Optional: Set JWT secret (development default provided)
export JWT_SECRET="your-secret-key-here"

# Optional: Set API key for token generation
export AUTH_API_KEY="your-api-key-here"
```

### 4. Database Schema
```sql
-- Apply the schema from db/schema.sql to your PostgreSQL database
psql $DATABASE_URL -f db/schema.sql
```

### 5. Run Development Server
```bash
# Method 1: Direct execution
python3 app.py

# Method 2: Flask CLI with debug mode
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=8080 --debug

# Method 3: With environment variables
FLASK_ENV=development python app.py
```

## 📚 API Documentation

### Authentication Endpoints

#### Generate JWT Token
```http
POST /api/auth/token
Content-Type: application/json

{
  "userId": "user-123",
  "email": "user@example.com",
  "sessionId": "session-abc",
  "apiKey": "optional-api-key"
}
```

### Avatar Endpoints

All avatar endpoints require authentication via `Authorization: Bearer <token>` header.

#### List User Avatars
```http
GET /api/users/{user_id}/avatars
Authorization: Bearer <jwt_token>
X-User-Email: user@example.com
X-Session-Id: session-abc
```

#### Create Avatar
```http
POST /api/users/{user_id}/avatars
Content-Type: application/json
Authorization: Bearer <jwt_token>
X-User-Email: user@example.com
X-Session-Id: session-abc

{
  "name": "My Avatar",
  "gender": "female",
  "ageRange": "adult",
  "creationMode": "manual",
  "source": "web",
  "quickMode": true,
  "basicMeasurements": {
    "height": 172.5,
    "weight": 65.0
  },
  "bodyMeasurements": {
    "chest": 95.2,
    "waist": 70.5
  },
  "morphTargets": [
    {
      "id": "morph_1",
      "sliderValue": 0.75,
      "unrealValue": 1.2
    }
  ],
  "quickModeSettings": {
    "bodyShape": "hourglass",
    "athleticLevel": "high",
    "measurements": {
      "waistCircumference": 70.5
    }
  }
}
```

#### Get Specific Avatar
```http
GET /api/users/{user_id}/avatars/{avatar_id}
Authorization: Bearer <jwt_token>
X-User-Email: user@example.com
X-Session-Id: session-abc
```

#### Update Avatar
```http
PUT /api/users/{user_id}/avatars/{avatar_id}
Content-Type: application/json
Authorization: Bearer <jwt_token>
X-User-Email: user@example.com
X-Session-Id: session-abc

{
  "name": "Updated Avatar Name",
  "quickModeSettings": null  // Clears quick mode settings
}
```

#### Delete Avatar
```http
DELETE /api/users/{user_id}/avatars/{avatar_id}
Authorization: Bearer <jwt_token>
X-User-Email: user@example.com
X-Session-Id: session-abc
```

## 🧪 Testing

### Run Test Suite
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_avatar_routes.py -v

# Run with coverage
python -m pytest tests/ --cov=avatar --cov=auth
```

### Manual API Testing
```bash
# Health check
curl https://tea9as8upn.eu-central-1.awsapprunner.com/health

# Generate token (requires API key in production)
curl -X POST https://tea9as8upn.eu-central-1.awsapprunner.com/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user", "email": "test@example.com", "sessionId": "test-session"}'

# List avatars (requires valid token)
curl https://tea9as8upn.eu-central-1.awsapprunner.com/api/users/test-user/avatars \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "X-User-Email: test@example.com" \
  -H "X-Session-Id: test-session"
```

## 🔧 Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string (required)
- `JWT_SECRET`: Secret key for JWT signing (optional, development default provided)
- `JWT_ALGORITHM`: JWT algorithm (default: HS256)
- `JWT_EXP_SECONDS`: Token expiration time in seconds (default: 3600)
- `AUTH_API_KEY`: API key for token generation (optional)
- `CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins

### Supported Data Types

#### Gender Options
- `female`, `male`, `non_binary`, `unspecified`

#### Age Range Options
- Internal: `child`, `teen`, `young_adult`, `adult`, `mature`, `senior`
- UI Labels: `15-19`, `20-29`, `30-39`, `40-49`, `50-59`, `60-69`, `70-79`, `80-89`, `90-99`

#### Creation Modes
- `manual`, `scan`, `preset`, `import`

#### Sources
- `web`, `ios`, `android`, `kiosk`, `api`, `integration`

## 📊 Database Schema

The application uses PostgreSQL with the following main tables:
- **users**: User account information and session data
- **avatars**: Core avatar data with metadata
- **avatar_basic_measurements**: Basic body measurements
- **avatar_body_measurements**: Detailed body measurements
- **avatar_morph_targets**: Morphological target configurations
- **avatar_quickmode_settings**: Quick mode presets with JSONB data
- **morph_definitions**: Reusable morph target definitions

## 🚀 Deployment

### AWS App Runner Deployment
1. Code pushed to `main` branch triggers automatic deployment
2. AWS App Runner builds container from source
3. Health check validates deployment at `/health`
4. Traffic switches to new version upon successful deployment

### Production Considerations
- Ensure `DATABASE_URL` is configured in production
- Set secure `JWT_SECRET` in production environment
- Configure `AUTH_API_KEY` for token generation security
- Set appropriate `CORS_ALLOWED_ORIGINS` for client applications

## 🔒 Security Features

- JWT-based stateless authentication
- Request validation and sanitization
- SQL injection prevention via parameterized queries
- CORS protection with configurable origins
- Transaction-based data consistency
- User access control and authorization checks

## 📝 License

This project is part of the FitSpace application ecosystem.