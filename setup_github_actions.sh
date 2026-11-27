#!/usr/bin/env bash
# setup_github_actions.sh - One-command setup for GitHub Actions scraping

set -e

REPO_NAME="gmaps-sleman-scrape"
GH_USER="${1:-$(gh api user --jq .login 2>/dev/null || echo 'YOUR_USERNAME')}"

echo "=== GitHub Actions Scraper Setup ==="
echo "Repo: $GH_USER/$REPO_NAME"
echo ""

# Check gh CLI
if ! command -v gh &> /dev/null; then
    echo "Installing GitHub CLI..."
    winget install GitHub.cli 2>/dev/null || brew install gh 2>/dev/null || sudo apt install gh 2>/dev/null
fi

# Authenticate
echo "Authenticating..."
gh auth status || gh auth login

# Create repo (public for free Actions)
echo "Creating repository..."
gh repo create "$GH_USER/$REPO_NAME" --public --source=. --push --description "Sleman Google Maps Parallel Scraper"

# Enable Actions
echo "Enabling GitHub Actions..."
gh api -X PUT "repos/$GH_USER/$REPO_NAME/actions/permissions" -f enabled=true -f allowed_actions=all

# Push workflow
echo "Pushing workflow..."
git add .github/workflows/scrape.yml Dockerfile.scrape scrape_in_container.py
git commit -m "Add GitHub Actions parallel scraper" || true
git push

echo ""
echo "=== SETUP COMPLETE ==="
echo ""
echo "NEXT STEPS:"
echo "1. Go to: https://github.com/$GH_USER/$REPO_NAME/actions"
echo "2. Click 'Google Maps Parallel Scrape' workflow"
echo "3. Click 'Run workflow' → Select 4 parallel jobs → Run"
echo "4. Wait 2-3 hours"
echo "5. Download 'competitive-map-master' artifact"
echo ""
echo "MONITOR:"
echo "  gh run watch --repo $GH_USER/$REPO_NAME"
echo ""
echo "DOWNLOAD RESULTS:"
echo "  gh run download --repo $GH_USER/$REPO_NAME --name competitive-map-master"