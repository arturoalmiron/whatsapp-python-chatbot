@echo off
echo ====================================
echo Hospital WhatsApp Chatbot Setup
echo ====================================
echo.

echo Checking Python installation...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found! Please install Python 3.10+ first.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo Installing Python dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Checking Ollama installation...
curl -s http://localhost:11434/api/tags > nul
if %errorlevel% neq 0 (
    echo WARNING: Ollama not running or not installed.
    echo Please install Ollama from: https://ollama.ai/download
    echo Then run: ollama pull gemma3:1b-it-qat
    pause
)

echo.
echo Creating directories...
if not exist "conversations" mkdir conversations
if not exist "logs" mkdir logs

echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Create .env file with your API tokens
echo 2. Get WaSender API token from wasenderapi.com
echo 3. Run: python script.py
echo.
echo See README_HOSPITAL_DEPLOYMENT.md for detailed instructions.
pause 