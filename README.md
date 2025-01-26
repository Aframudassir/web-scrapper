# StubHub Event Ticket Scraper

## Project Overview
This Python project scrapes event and ticket listings from StubHub, focusing on retrieving detailed ticket information while applying specific filters.

## Prerequisites
- Python 3.8+
- Stable internet connection
- 5 provided sticky proxies

## Setup Instructions

### 1. Create a Virtual Environment
```bash
# For Windows
python -m venv scraper_env

# For macOS/Linux
python3 -m venv scraper_env

# Activate the virtual environment
# Windows
scraper_env\Scripts\activate

# macOS/Linux
source scraper_env/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Proxies
Before running the script, ensure you have configured the 5 sticky proxies in the `web_scrapper.py` script.

### 4. Run the Scraper
```bash
python web_scrapper.py
```

## Output
- Scraping results will be stored in `events_data.json`
- Logs will be saved in `scraper.log`

## Performance Expectations
- Average scrape time per event: < 2 seconds
- Maximum failed attempts: < 15%

## Notes
- Recommended Tickets filter is set to False
- BetterValueTickets filter is set to False
- Uses API requests only (no browser automation)

## Troubleshooting
- Ensure all dependencies are correctly installed
- Verify proxy configurations
- Check network connectivity
- Review logs for any specific errors
