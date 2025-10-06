# Fitspace Backend API

A Flask-based REST API for the Fitspace application, deployed on AWS App Runner with PostgreSQL database.

## 🚀 Live Deployment

- **Production URL**: https://tea9as8upn.eu-central-1.awsapprunner.com
- **Health Check**: https://tea9as8upn.eu-central-1.awsapprunner.com/health
- **Auto-Deploy**: ✅ Enabled on `main` branch

## 🛠️ Local Development Setup

### Prerequisites
- Python 3.8+
- Git

### 1. Clone Repository
```bash
git clone https://github.com/e-kipica/fitspace-backend.git
cd fitspace-backend
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Verify activation (should show venv path)
which python
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup

Set the `DATABASE_URL` environment variable to point to your PostgreSQL instance and apply the schema migrations:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/fitspace"

# Apply schema (idempotent)
psql "$DATABASE_URL" -f db/schema.sql
```

This script creates the required tables (`users`, `avatars`, `avatar_basic_measurements`, `avatar_body_measurements`, and `avatar_morph_targets`) and enforces the five-avatar-per-user quota via a slot constraint.

#### Auth session metadata columns

The `users` table now persists additional authentication metadata so that avatar requests can be correlated with the active session:

- `email` – optional email address associated with the identity (case-insensitive unique index)
- `session_id` – identifier of the active session (unique index)
- `issued_at` / `expires_at` – timestamps describing the validity window of the access token
- `access_token` – last access token observed for the user
- `refresh_token` – last refresh token observed for the user
- `updated_at` – automatically updated on every write

> **Migrating existing databases**
>
> Apply the following statements if your database already contains the previous `users` schema:
>
> ```sql
> ALTER TABLE users
>     ADD COLUMN IF NOT EXISTS email TEXT,
>     ADD COLUMN IF NOT EXISTS session_id TEXT,
>     ADD COLUMN IF NOT EXISTS issued_at TIMESTAMPTZ,
>     ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
>     ADD COLUMN IF NOT EXISTS access_token TEXT,
>     ADD COLUMN IF NOT EXISTS refresh_token TEXT,
>     ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
>
> CREATE UNIQUE INDEX IF NOT EXISTS users_email_key
>     ON users (LOWER(email)) WHERE email IS NOT NULL;
> CREATE UNIQUE INDEX IF NOT EXISTS users_session_id_key
>     ON users (session_id) WHERE session_id IS NOT NULL;
> ```

#### Avatar metadata columns

The `avatars` table captures additional metadata used by the Fitspace clients when generating avatars. Each value is validated by the API and stored in the database for auditing purposes:

- `gender` – one of `female`, `male`, `non_binary`, `unspecified`
- `age_range` – one of `child`, `teen`, `young_adult`, `adult`, `mature`, `senior`
- `creation_mode` – one of `manual`, `scan`, `preset`, `import`
- `source` – one of `web`, `ios`, `android`, `kiosk`, `api`, `integration`
- `quick_mode` – boolean flag indicating if the avatar was generated via the quick workflow (defaults to `false`)
- `created_by_session` – optional session identifier that created the avatar (separate from the owning user ID)

> **Migrating existing databases**
>
> Apply the following statements if you are extending a pre-existing `avatars` table:
>
> ```sql
> ALTER TABLE avatars
>     ADD COLUMN IF NOT EXISTS gender TEXT,
>     ADD COLUMN IF NOT EXISTS age_range TEXT,
>     ADD COLUMN IF NOT EXISTS creation_mode TEXT,
>     ADD COLUMN IF NOT EXISTS source TEXT,
>     ADD COLUMN IF NOT EXISTS quick_mode BOOLEAN NOT NULL DEFAULT FALSE,
>     ADD COLUMN IF NOT EXISTS created_by_session TEXT;
> ```

### 5. Run Local Development Server
```bash
# Method 1: Direct Python execution
python3 app.py

# Method 2: Using Flask CLI with debug mode
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=8080 --debug

# Method 3: With environment variables
FLASK_ENV=development python app.py
```

### 6. Test Local Application
Open your browser or use curl:
```bash
# Test main endpoint
curl http://localhost:8080/
# Expected: {"message": "Fitspace Backend API"}

# Test health endpoint
curl http://localhost:8080/health
# Expected: {"status": "healthy"}
```

## 🚀 Deployment Information

### Deployment Process
1. Code pushed to `main` branch
2. AWS App Runner detects changes
3. Builds new container with your code
4. Deploys to production URL
5. Health check validates deployment
6. Traffic switches to new version

## 🧪 Testing

### Local Testing
```bash
# Run all endpoints locally
curl http://localhost:8080/
curl http://localhost:8080/health
```
# Run unit tests (validation coverage for avatar metadata)
python -m unittest discover -s tests

### 🔐 Authentication

- Configure a JWT secret (recommended):
  ```bash
  export JWT_SECRET="super-secret-value"
  ```
- Optionally protect token issuance with an API key:
  ```bash
  export AUTH_API_KEY="backend-shared-key"
  ```
- Configure allowed origins for CORS (comma-separated, or `*` to allow all origins):
  ```bash
  export CORS_ALLOWED_ORIGINS="http://localhost:5177,https://app.example.com"
  ```
- Obtain an access token for a user:
  ```bash
  curl -X POST http://localhost:8080/api/auth/token \
    -H "Content-Type: application/json" \
    -d '{"userId": "user-123", "apiKey": "backend-shared-key", "email": "user@example.com", "sessionId": "session-abc", "refreshToken": "refresh-xyz"}'
  ```
  Response contains the issued/expiry timestamps, the `Authorization` header and convenience headers (`X-User-Email`, `X-Session-Id`, `X-Refresh-Token`) ready for avatar routes.

- When calling avatar endpoints you must forward the issued headers (or equivalent values) with each request:
  ```bash
  curl http://localhost:8080/api/users/user-123/avatars \
    -H "Authorization: Bearer <token>" \
    -H "X-User-Email: user@example.com" \
    -H "X-Session-Id: session-abc" \
    -H "X-Refresh-Token: refresh-xyz"
  ```
  Missing `X-User-Email` or `X-Session-Id` headers will result in a `400` response.

### Production Testing
```bash
# Test production deployment
curl https://tea9as8upn.eu-central-1.awsapprunner.com/
curl https://tea9as8upn.eu-central-1.awsapprunner.com/health
```
### Avatar metadata scenarios

Example request payload that exercises the extended avatar metadata (matching the validation rules enforced by the API):

```json
{
  "name": "Runner",
  "gender": "female",
  "ageRange": "adult",
  "creationMode": "manual",
  "source": "web",
  "quickMode": true,
  "createdBySession": "session-xyz",
  "basicMeasurements": {
    "height": 172.4
  },
  "bodyMeasurements": {
    "waist": 81.2
  },
  "morphTargets": [
    {"id": "leg_length", "value": 0.25}
  ]
}
```

The accompanying unit tests in `tests/test_avatar_routes.py` cover both valid and invalid combinations so that integrations can rely on consistent HTTP 400 responses when a value falls outside the documented ranges.

## ⚙️ Frontend konfiguracija avatara

Da bi frontend koristio ovaj backend servis, konfiguriraj varijablu okruženja `VITE_AVATAR_API_BASE_URL` tako da pokazuje na bazni URL koji već završava s `/api/users/`. Servis `avatarApi` unutar frontenda interpolira `userId` u nastavak putanje (npr. `http://localhost:8080/api/users/<USER_ID>/avatars`), pa je obavezan završni kosac prije interpolacije korisničkog identifikator