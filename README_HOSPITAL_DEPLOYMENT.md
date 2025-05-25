# Hospital WhatsApp Chatbot - Deployment Guide

## System Requirements
- Windows 10/11 or Ubuntu 20.04+
- Python 3.10 or higher
- Internet connection for initial setup
- 2GB RAM minimum, 4GB recommended

## Pre-Installation Setup

### 1. Install Python
Download from: https://www.python.org/downloads/
- ✅ Check "Add Python to PATH" during installation

### 2. Install Ollama (Local AI)
Download from: https://ollama.ai/download
- Install and run: `ollama pull gemma3:1b-it-qat`

## Installation Steps

### 1. Extract Files
- Extract the project ZIP to: `C:\Hospital\WhatsAppBot\`

### 2. Install Dependencies
Open Command Prompt as Administrator:
```bash
cd C:\Hospital\WhatsAppBot
pip install -r requirements.txt
```

### 3. Configure Environment
Create `.env` file with:
```
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:1b-it-qat

# WaSender API (get from wasenderapi.com)
WASENDER_API_TOKEN=your_token_here

# Per-user limits
RATE_LIMIT_PER_MINUTE=5
RATE_LIMIT_PER_HOUR=30

# Global limits (adjust based on server power)
GLOBAL_RATE_LIMIT_PER_MINUTE=100
GLOBAL_RATE_LIMIT_PER_HOUR=1000
```

### 4. Get WhatsApp API Token
1. Sign up at: https://wasenderapi.com/
2. Add hospital phone number
3. Scan QR code with hospital WhatsApp
4. Copy API token to `.env` file

## Running the Bot

### Start Services
```bash
# 1. Start Ollama (if not running)
ollama serve

# 2. Start the chatbot
python script.py
```

### Verify Installation
Test with:
```bash
curl -X POST http://localhost:5001/webhook -H "Content-Type: application/json" -d "{\"from\": \"test123\", \"body\": \"Hola\"}"
```

Expected response: `{"reply":"¿Cuál es su nombre completo?"}`

## Features
- ✅ Spanish language support
- ✅ Appointment booking (Nombre, Fecha, Departamento, ID)
- ✅ Date validation (business hours, weekdays only)
- ✅ Local AI (no external API costs)
- ✅ Insurance checking (ready for database integration)
- ✅ Rate limiting (5 messages/minute, 30 messages/hour per user)
- ✅ Admin monitoring endpoints
- ✅ Automatic cleanup of old data

## Rate Limiting & Security
The system includes built-in protection against abuse with **two-level rate limiting**:

### Per-User Limits (Individual Protection)
- **5 messages per minute** per WhatsApp number
- **30 messages per hour** per WhatsApp number
- Prevents individual users from spamming the system

### Global Limits (Server Protection)
- **100 requests per minute** across all users
- **1000 requests per hour** across all users
- Protects server from being overwhelmed by too many simultaneous users

### Additional Features
- Automatic cleanup of old rate limit data
- Spanish error messages for rate limit violations
- Admin endpoints for monitoring usage
- **Easy configuration** via environment variables

### Configuring Rate Limits
Add to your `.env` file to customize limits based on your server capacity:
```env
# Per-user limits
RATE_LIMIT_PER_MINUTE=5
RATE_LIMIT_PER_HOUR=30

# Global limits (adjust based on server power)
GLOBAL_RATE_LIMIT_PER_MINUTE=100
GLOBAL_RATE_LIMIT_PER_HOUR=1000
```

### Admin Endpoints
- `GET /admin/status` - System health, global usage statistics, and server load
- `GET /admin/rate-limits/{user_id}` - Rate limit status for specific user

Example admin status check:
```bash
curl http://localhost:5001/admin/status
```

**Global usage example response:**
```json
{
  "global_usage": {
    "requests_last_minute": 15,
    "requests_last_hour": 245,
    "minute_limit": 100,
    "hour_limit": 1000,
    "minute_usage_percent": 15.0,
    "hour_usage_percent": 24.5
  }
}
```

## Troubleshooting
- **Port 5001 blocked**: Change port in script.py
- **Ollama not responding**: Restart Ollama service
- **WhatsApp not working**: Check WaSender token and webhook URL

## Database Integration (When Ready)
1. Replace simulated storage in `script.py` lines 243-244
2. Add database connection in `check_insurance()` function
3. Update appointment saving logic

## Security Notes
- Run on internal network only
- Use hospital firewall rules
- Regular security updates for Python packages

## Support Contact
[Your contact information here] 