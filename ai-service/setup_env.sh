#!/usr/bin/env zsh
echo "🧹 Cleaning up existing AI service environment (Mac/Zsh)..."

echo "Checking Python 3.10+ ..."
if ! command -v python &> /dev/null; then
    echo "🚨 Python not found. Please install Python 3.10+"
    exit 1
fi

echo "❌ Removing old caches and environments if exist..."
find . -name "*.pyc" -exec rm -rf {} +
find . -name "__pycache__" -exec rm -rf {} +
rm -rf .pytest_cache .coverage .tox .venv venv env 

echo "🛠 Creating fresh virtual environment (*venv*)..."
python3 -m venv venv
source venv/bin/activate

echo "📦 Reinstalling dependencies from requirements.txt..."
python -m pip install --upgrade pip
python -m pip install "numpy<2.0.0"  # Ensure numpy < 2.0.0
python -m pip install -r requirements.txt --no-cache-dir

echo "\n✅ Fresh AI Service Python Environment Setup Complete!"
echo "📍 Run with: source venv/bin/activate && uvicorn main:app --port 8001 --reload"
