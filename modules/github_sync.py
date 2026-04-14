import subprocess
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class GitHubSync:
    def __init__(self, config: dict):
        self.config = config
        self.enabled = config['github']['enabled']
        self.repo_path = config['github']['repo_path'] or Path.cwd()
        self.auto_push = config['github']['auto_push']

    def is_repo(self) -> bool:
        """Check if current directory is a git repo."""
        try:
            subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except:
            return False

    def commit_and_push(self, run_stats: dict) -> bool:
        """Commit and push changes to GitHub."""
        if not self.enabled:
            logger.info("GitHub sync disabled")
            return True

        if not self.is_repo():
            logger.warning("Not a git repository - skipping sync")
            return False

        try:
            # Stage all changes in data/ and docs/
            logger.info("Staging changes...")
            subprocess.run(
                ['git', 'add', 'data/', 'docs/'],
                cwd=self.repo_path,
                capture_output=True,
                timeout=10
            )

            # Check if there are changes to commit
            status = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if not status.stdout.strip():
                logger.info("No changes to commit")
                return True

            # Create commit message
            commit_msg = self._create_commit_message(run_stats)

            # Commit
            logger.info(f"Committing: {commit_msg}")
            commit = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if commit.returncode != 0:
                logger.warning(f"Commit failed: {commit.stderr}")
                return False

            # Push if enabled
            if self.auto_push:
                logger.info("Pushing to GitHub...")
                push = subprocess.run(
                    ['git', 'push'],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if push.returncode != 0:
                    logger.error(f"Push failed: {push.stderr}")
                    logger.warning("Local commit succeeded, but push failed - will retry next cycle")
                    return False

                logger.info("Successfully pushed to GitHub")

            return True

        except subprocess.TimeoutExpired:
            logger.error("Git operation timed out")
            return False
        except Exception as e:
            logger.error(f"GitHub sync failed: {str(e)}")
            return False

    def _create_commit_message(self, run_stats: dict) -> str:
        """Create a commit message from run statistics."""
        template = self.config['github']['commit_message_template']

        message = template.format(
            date=datetime.now().strftime('%Y-%m-%d %H:%M'),
            symbol_count=run_stats.get('signals_generated', 0),
            trade_count=run_stats.get('trades_opened', 0)
        )

        return message

    def update_dashboard(self, portfolio_data: dict):
        """Update GitHub Pages dashboard data."""
        try:
            docs_folder = Path(self.config['dashboard']['docs_folder'])
            docs_folder.mkdir(exist_ok=True)

            data_file = docs_folder / 'data.json'

            # Read existing data if available
            if data_file.exists():
                with open(data_file, 'r') as f:
                    dashboard_data = json.load(f)
            else:
                dashboard_data = {'history': []}

            # Add current portfolio state
            current_snapshot = {
                'timestamp': datetime.now().isoformat(),
                'equity': portfolio_data['equity'],
                'cash': portfolio_data['cash'],
                'pnl': portfolio_data['total_pnl'],
                'win_rate': portfolio_data['win_rate'],
                'trades': portfolio_data['trades_count']
            }

            dashboard_data['latest'] = current_snapshot
            dashboard_data['history'].append(current_snapshot)

            # Keep only last 100 snapshots
            if len(dashboard_data['history']) > 100:
                dashboard_data['history'] = dashboard_data['history'][-100:]

            # Write updated data
            with open(data_file, 'w') as f:
                json.dump(dashboard_data, f, indent=2)

            logger.info(f"Updated dashboard data at {data_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to update dashboard: {str(e)}")
            return False
