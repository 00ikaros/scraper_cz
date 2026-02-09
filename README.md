# 📜 Bloomberg Law Scraper

An interactive web application for scraping legal transcripts from Bloomberg Law with real-time user control and feedback.

## ✨ Features

- 🔐 **Secure Login** - Credentials stored in environment variables
- 🔍 **Smart Search** - Interactive court selection with fuzzy matching
- 📄 **Flexible Scraping** - Choose which transcripts to download
- ⚡ **Real-time Updates** - Live progress tracking via WebSocket
- 🎨 **Beautiful UI** - Modern, responsive control panel
- 📊 **Job Management** - Track and manage scraping jobs
- 💾 **Automatic Downloads** - PDFs saved with organized naming
- 📝 **Comprehensive Logging** - Detailed logs for debugging

## 🏗️ Architecture
```
Bloomberg Law Scraper
├── Backend (Python + FastAPI + Playwright)
│   ├── REST API for job management
│   ├── WebSocket for real-time communication
│   └── Playwright-based browser automation
│
├── Frontend (Vanilla JS + HTML + CSS)
│   ├── Interactive control panel
│   ├── Real-time status updates
│   └── Court & transcript selection UI
│
└── State Machine
    ├── Login → Search → Results → Documents
    └── Interactive pauses for user input
```

## 📋 Prerequisites

- Python 3.10 or higher
- Bloomberg Law account with valid credentials
- Google Chrome or Chromium browser (installed automatically by Playwright)

## 🚀 Quick Start

### 1. Clone or Extract the Project
```bash
cd bloomberg-scraper
```

### 2. Install Dependencies
```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 3. Configure Credentials
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Bloomberg Law credentials
nano .env  # or use any text editor
```

Update these values in `.env`:
```bash
BLOOMBERG_USERNAME=your_actual_username
BLOOMBERG_PASSWORD=your_actual_password
```

### 4. Run the Application
```bash
# Quick start (recommended)
python run.py

# Or run directly
python main.py
```

### 5. Open the Control Panel

Open your browser and navigate to:
```
http://localhost:8000
```

## 📖 Usage Guide

### Basic Workflow

1. **Start the Application**
```bash
   python run.py
```

2. **Open Control Panel**
   - Navigate to `http://localhost:8000` in your browser
   - Wait for "Connected" status indicator

3. **Configure Search**
   - **Keywords**: e.g., "transcript"
   - **Court Name**: e.g., "U.S. Bankruptcy Court District of Nevada"
   - **Judge Name**: e.g., "Markell"
   - **Number of Documents**: Leave empty for all on page, or specify a number (1-50)

4. **Start Scraping**
   - Click "🚀 Start Scraping"
   - Watch real-time progress in the Activity Log

5. **Interactive Selection**
   - **Court Selection**: When multiple courts match, select the correct one
   - **Transcript Selection**: Choose which transcript entries to download
     - ✓ Download Selected
     - ⬇️ Download All
     - ⏭️ Skip Document

6. **Monitor Progress**
   - View current state and progress bar
   - Check downloaded files in the Downloads panel
   - Review activity log for detailed information

7. **Access Downloads**
   - Files are saved to `./downloads/` directory
   - Naming format: `{docket_number}_entry_{entry_num}.pdf`

### Configuration Options

Edit `.env` to customize behavior:
```bash
# Browser Settings
HEADLESS_MODE=false          # Set to true to hide browser window
BROWSER_TIMEOUT=60000        # Timeout in milliseconds

# Scraping Mode
SCRAPING_MODE=FULLY_INTERACTIVE
# Options:
# - FULLY_INTERACTIVE: Pause for all selections
# - SEMI_AUTOMATED: Only pause when needed
# - FULLY_AUTOMATED: No pauses (requires exact inputs)

# Paths
DOWNLOADS_DIR=./downloads
LOGS_DIR=./logs
SCREENSHOTS_DIR=./screenshots
```

## 📁 Project Structure
```
bloomberg-scraper/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── requirements.txt        # Python dependencies
│   ├── .env                    # Configuration (create from .env.example)
│   │
│   ├── scraper/
│   │   ├── browser_manager.py           # Playwright browser
│   │   ├── bloomberg_scraper.py         # Main orchestrator
│   │   ├── state_machine.py             # State management
│   │   └── page_handlers/
│   │       ├── page1_login_search.py    # Login & search
│   │       ├── page2_results.py         # Results handling
│   │       └── page3_docket.py          # Docket & downloads
│   │
│   ├── api/
│   │   ├── websocket_handler.py   # WebSocket server
│   │   └── routes.py              # REST API
│   │
│   ├── models/
│   │   ├── events.py              # WebSocket events
│   │   └── scraping_job.py        # Job models
│   │
│   ├── config/
│   │   ├── settings.py            # Configuration
│   │   └── selectors.json         # CSS selectors
│   │
│   └── utils/
│       ├── logger.py              # Logging
│       └── helpers.py             # Utilities
│
├── frontend/
│   ├── index.html                 # Control panel
│   ├── css/
│   │   └── styles.css             # Styling
│   └── js/
│       ├── app.js                 # Main logic
│       ├── websocket-client.js    # WebSocket client
│       └── ui-components.js       # UI rendering
│
├── downloads/                     # Downloaded PDFs
├── logs/                          # Application logs
├── screenshots/                   # Debug screenshots
│
├── run.py                         # Quick start script
└── README.md                      # This file
```

## 🔧 Advanced Usage

### Customizing Transcript Patterns

Edit `config/selectors.json` to add custom transcript patterns:
```json
{
  "transcript_patterns": [
    {
      "id": "hearing_transcript",
      "pattern": "^Transcript regarding Hearing Held on",
      "enabled": true,
      "description": "Standard hearing transcript"
    },
    {
      "id": "trial_transcript",
      "pattern": "^Transcript of Trial",
      "enabled": true,
      "description": "Trial transcript"
    }
  ]
}
```

### API Endpoints

The application exposes REST API endpoints:

- `GET /` - Frontend control panel
- `GET /api/health` - Health check
- `POST /api/jobs/create` - Create scraping job
- `GET /api/jobs/{job_id}` - Get job status
- `GET /api/jobs/{job_id}/results` - Get job results
- `POST /api/jobs/{job_id}/cancel` - Cancel job
- `GET /api/jobs` - List all jobs
- `WS /ws?client_id={id}` - WebSocket connection

API Documentation: `http://localhost:8000/docs`

### Programmatic Usage
```python
from scraper.bloomberg_scraper import BloombergScraper
from models.scraping_job import ScrapingJob, SearchCriteria
from api.websocket_handler import ConnectionManager

# Create job
search_criteria = SearchCriteria(
    keywords="transcript",
    court_name="U.S. Bankruptcy Court District of Nevada",
    judge_name="Markell"
)

job = ScrapingJob(
    job_id="job_123",
    search_criteria=search_criteria,
    num_documents=5
)

# Run scraper
connection_manager = ConnectionManager()
scraper = BloombergScraper("client_id", connection_manager)
await scraper.run_scraping_job(job)
```

## 🐛 Troubleshooting

### Common Issues

**1. Login Fails**
- Verify credentials in `.env` file
- Check if Bloomberg Law changed their login page
- Review `logs/scraper_*.log` for details

**2. Court Not Found**
- Try a more specific or broader court name
- Check the interactive selection dialog
- Courts must be typed exactly as they appear in Bloomberg Law

**3. No Transcripts Found**
- Verify search criteria (keywords, court, judge)
- Check if transcripts exist for that case
- Review transcript patterns in `config/selectors.json`

**4. WebSocket Connection Failed**
- Ensure no firewall blocking port 8000
- Check if another application is using the port
- Try restarting the application

**5. Downloads Not Appearing**
- Check `downloads/` directory
- Verify file permissions
- Look for errors in Activity Log

### Debug Mode

Enable debug logging in `.env`:
```bash
LOG_LEVEL=DEBUG
HEADLESS_MODE=false  # See browser actions
```

Check logs:
```bash
# All logs
tail -f logs/scraper_*.log

# Errors only
tail -f logs/errors_*.log
```

Take screenshots on error (automatic):
```bash
ls screenshots/
```

## 📊 Performance Tips

- **Headless Mode**: Set `HEADLESS_MODE=true` for faster scraping
- **Batch Size**: Process 5-10 documents at a time for optimal speed
- **Network**: Ensure stable internet connection
- **Resources**: Close other browser tabs to free up memory

## 🔒 Security

- ✅ Credentials stored in `.env` (never commit to git)
- ✅ HTTPS for Bloomberg Law connections
- ✅ Session state management
- ✅ No credential logging
- ⚠️  `.env` is in `.gitignore` - keep it safe!

## 📜 License

This project is for educational and research purposes. Ensure compliance with Bloomberg Law's Terms of Service when using this tool.

## 🤝 Contributing

Suggestions and improvements welcome! Key areas:
- Additional court systems (PACER integration)
- Enhanced pattern matching
- Export formats (CSV, JSON)
- Scheduling capabilities

## 📧 Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs in `logs/` directory
3. Check `screenshots/` for visual debugging

## 🎯 Roadmap

- [ ] PACER integration
- [ ] Multi-user support
- [ ] Job scheduling
- [ ] Export to CSV/Excel
- [ ] Email notifications
- [ ] Docker deployment
- [ ] Cloud storage integration

---

**Happy Scraping! 📜✨**