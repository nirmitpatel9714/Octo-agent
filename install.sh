#!/bin/bash
set -e

echo "Installing Octo Agent..."

if ! command -v python &> /dev/null; then
    echo "Python is not installed. Attempting to install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install python
        else
            echo "Error: Homebrew is not installed. Please install Homebrew first, or install Python manually."
            exit 1
        fi
    elif command -v apt-get &> /dev/null; then
        echo "Detected Debian/Ubuntu. Installing python and python-venv..."
        sudo apt-get update
        sudo apt-get install -y python python-venv python-pip
    elif command -v dnf &> /dev/null; then
        echo "Detected Fedora/RHEL. Installing python..."
        sudo dnf install -y python
    elif command -v pacman &> /dev/null; then
        echo "Detected Arch Linux. Installing python..."
        sudo pacman -S --noconfirm python
    else
        echo "Error: Unsupported package manager. Please install Python manually."
        exit 1
    fi
    
    if ! command -v python &> /dev/null; then
        echo "Failed to install Python. Please install it manually."
        exit 1
    fi
    echo "Python installed successfully."
fi

echo "Moving all code to $HOME/octo..."
mkdir -p "$HOME/octo"
cp -r . "$HOME/octo/"
cd "$HOME/octo"

echo "Creating virtual environment in $HOME/octo/.venv..."
python -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt
pip install fastapi uvicorn[standard]

echo "Installation complete!"
echo "The code has been moved to $HOME/octo"
echo "Copying octo to /bin... (may require sudo password)"
sudo cp "$HOME/octo/bin/octo" /bin/octo
sudo chmod +x /bin/octo
echo "To use the octo command from anywhere, no PATH changes are needed as it's in /bin."
echo ""
echo "To onboard, run:"
echo "  octo onboard"
echo "To start the web dashboard, run:"
echo "  octo web"
