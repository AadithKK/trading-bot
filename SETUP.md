# Setup Guide - Local Trading Bot

## Prerequisites

- Windows 11
- Python 3.9+ installed
- Ollama installed and running
- Git installed (for GitHub sync)
- GitHub account (optional, for auto-push)

## Step 1: Install Python Dependencies

```bash
cd trading-bot-local
pip install -r requirements.txt
```

## Step 2: Start Ollama Server

Keep this running in a PowerShell window:

```powershell
ollama run gemma2:9b
```

**First time?** This downloads the model (1-2 GB). Subsequent runs start instantly.

**Alternative models:** Replace `gemma2:9b` with:
- `gemma2:2.2b` (faster, lighter)
- `mistral:latest` (better quality)
- Any model from `ollama list`

## Step 3: Configure the Bot

Edit `config.json` to customize:

- **Trading parameters**: Position size, stop loss, take profit
- **Watchlist**: Add/remove symbols
- **Ollama**: Point to your local server
- **GitHub**: Enable/disable auto-push

Default settings work for paper trading. No changes needed for MVP testing.

## Step 4: Run a Test

```bash
python main.py --status
```

This shows your current portfolio (should show $10,000 starting balance).

```bash
python main.py --force
```

This runs a full trading cycle with all 13 core symbols. Takes ~30-60 seconds.

**Expected output:**
- Scans symbols, generates signals
- Ollama reviews candidates
- May execute 0-3 paper trades
- Saves results to `data/` folder
- Creates `logs/system.log`

Check `logs/system.log` if anything fails.

## Step 5: Set Up Windows Task Scheduler

The bot should run automatically every morning at 8:20 AM (before market open).

### Option A: Automatic Script (Recommended)

```powershell
# Run this PowerShell script as Administrator
# It creates the task for you

$botPath = "C:\Users\kanno\OneDrive\Desktop\Ai stuff for Ai\trading-bot-local"
$scriptPath = "$botPath\run_bot.bat"

$trigger = New-ScheduledTaskTrigger -Daily -At "08:20"
$action = New-ScheduledTaskAction -Execute $scriptPath
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBattery

Register-ScheduledTask -TaskName "Trading Bot Daily" `
  -Trigger $trigger `
  -Action $action `
  -Settings $settings `
  -Description "Runs trading bot daily at 8:20 AM"

Write-Host "✓ Task created! Check Task Scheduler to verify."
```

### Option B: Manual (Via Task Scheduler GUI)

1. Open **Task Scheduler** (search in Windows Start menu)
2. Click **Create Basic Task** (right panel)
3. **Name:** Trading Bot Daily
4. **Trigger:** Daily at 8:20 AM
5. **Action:** Start a program
   - Program: `C:\Users\kanno\OneDrive\Desktop\Ai stuff for Ai\trading-bot-local\run_bot.bat`
6. Click OK

## Step 6: GitHub Sync (Optional)

If you want auto-push to GitHub:

1. Initialize a git repo:
   ```bash
   cd trading-bot-local
   git init
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git add .
   git commit -m "Initial commit"
   git push -u origin main
   ```

2. Edit `config.json`:
   ```json
   "github": {
     "enabled": true,
     "auto_push": true,
     "repo_path": "C:\\path\\to\\trading-bot-local"
   }
   ```

3. After each bot run, results auto-commit and push

## Verifying Everything Works

### 1. Check Ollama Connection

```bash
python main.py --force
```

Look for this in logs:
- `Ollama server: AVAILABLE` ✓ Good!
- `Ollama unavailable, falling back to rules` ⚠️ But still works (uses rules instead)

### 2. Check Portfolio Saved

After running, check:
- `data/portfolio.json` - should have your current state
- `data/trade_log.csv` - closed trades (empty until first closes)
- `data/signals.json` - latest signal scores
- `logs/system.log` - full run details

### 3. Check Scheduling

Look at Task Scheduler:
1. Open Task Scheduler
2. Find "Trading Bot Daily"
3. Right-click → View all properties
4. Check trigger is set to 8:20 AM daily

## Troubleshooting

### Bot won't start
```bash
python main.py --force
```
Check `logs/system.log` for errors.

### Ollama connection failed
- Verify Ollama is running: `ollama list` in PowerShell
- Default URL: `http://localhost:11434`
- If different, edit `config.json` -> `ollama` -> `base_url`

### No trades executing
- Check cash balance: `python main.py --status`
- Need ≥ $500 available for trades
- Check signal scores in `data/signals.json`
- Verify RSI and trend conditions in `config.json`

### Task Scheduler not running
- Check: Is the bot's PowerShell script valid?
- Run task manually: Right-click task → Run
- Check logs: `logs/scheduler.log`

### GitHub push fails
- Verify git credentials saved: `git config --list`
- Check repo URL: `git remote -v`
- For HTTPS: Use personal access token, not password
- Enable auto_push: false in config to disable

## Next Steps

1. **Monitor first week** - Let it trade for 5-10 cycles
2. **Analyze results** - Check `data/trade_log.csv` for patterns
3. **Tune parameters** - Edit `config.json` based on what worked/failed
4. **Dashboard** - Push to GitHub to enable GitHub Pages dashboard
5. **Add symbols** - Expand watchlist as confidence grows

## Daily Workflow

Once running, you don't need to do anything:

1. **8:20 AM** - Bot runs automatically (Task Scheduler)
2. **Data saved** - Results in `data/portfolio.json`
3. **GitHub pushed** - If enabled, repo updates auto matically
4. **Dashboard refreshes** - GitHub Pages site shows latest equity

## Getting Help

**Check logs first:**
```bash
cat logs\system.log
```

**Run manual test:**
```bash
python main.py --force --status
```

**Inspect portfolio:**
```bash
type data\portfolio.json
```

Everything is logged and saved. No data is lost on crashes.

## Safety Notes

- ✓ Paper trading only - no real money
- ✓ All trades are simulated
- ✓ Historical data never deleted
- ✓ Can safely cancel Task Scheduler any time
- ✓ Portfolio persists across restarts

Have questions? Check README.md for detailed documentation.
