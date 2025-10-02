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

### 4. Run Local Development Server
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

### Production Testing
```bash
# Test production deployment
curl https://tea9as8upn.eu-central-1.awsapprunner.com/
curl https://tea9as8upn.eu-central-1.awsapprunner.com/health
```
