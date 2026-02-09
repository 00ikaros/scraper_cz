"""
Quick start script for Bloomberg Law Scraper
"""
import subprocess
import sys
import os
from pathlib import Path


def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    try:
        import fastapi
        import playwright
        import loguru
        print("✓ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e.name}")
        print("\n Please install dependencies:")
        print("   pip install -r requirements.txt")
        print("   playwright install chromium")
        return False


def check_env_file():
    """Check if .env file exists"""
    env_file = Path("backend/.env")

    if not env_file.exists():
        print("\n  .env file not found!")
        print("\n Creating .env file from template...")

        # Copy from .env.example
        example_file = Path("backend/.env.example")
        if example_file.exists():
            import shutil
            shutil.copy(example_file, env_file)
            print("✓ Created .env file")
            print("\n⚠️  IMPORTANT: Edit backend/.env file and add your Bloomberg Law credentials!")
            print("   Open backend/.env and set:")
            print("   - BLOOMBERG_USERNAME=your_username")
            print("   - BLOOMBERG_PASSWORD=your_password")
            return False
        else:
            print("❌ backend/.env.example not found. Please create .env manually.")
            return False

    # Check if credentials are set
    with open(env_file, 'r') as f:
        content = f.read()
        if 'your_username_here' in content or 'your_password_here' in content:
            print("\n  Please update your credentials in backend/.env file!")
            return False

    print("✓ .env file configured")
    return True


def check_directories():
    """Ensure required directories exist"""
    print("\n📁 Checking directories...")
    
    directories = ['downloads', 'logs', 'screenshots']
    
    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
            print(f"✓ Created {directory}/ directory")
        else:
            print(f"✓ {directory}/ directory exists")
    
    return True


def start_server():
    """Start the FastAPI server"""
    print("\n Starting Bloomberg Law Scraper...")
    print("=" * 60)
    print(" Backend API: http://localhost:8000")
    print(" Control Panel: http://localhost:8000")
    print(" API Docs: http://localhost:8000/docs")
    print("=" * 60)
    print("\n Tips:")
    print("   - Open http://localhost:8000 in your browser")
    print("   - Use Ctrl+C to stop the server")
    print("   - Check logs/ directory for detailed logs")
    print("\n" + "=" * 60 + "\n")
    
    try:
        # Run the main application from backend directory
        subprocess.run([sys.executable, "main.py"], cwd="backend", check=True)
    except KeyboardInterrupt:
        print("\n\n Shutting down gracefully...")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running server: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    print("=" * 60)
    print("Bloomberg Law Scraper - Quick Start")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check .env file
    if not check_env_file():
        print("\n  Please configure .env file before continuing.")
        sys.exit(1)
    
    # Check directories
    check_directories()
    
    # Start server
    start_server()


if __name__ == "__main__":
    main()