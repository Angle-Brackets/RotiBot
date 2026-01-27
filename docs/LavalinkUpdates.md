# Automatic Lavalink Plugin Updates

RotiBot includes an automated system for keeping Lavalink plugins up-to-date.

## How It Works

### Automated Workflow

A GitHub Actions workflow runs **daily at 2 AM UTC** to:

1. 🔍 Check Maven repositories for new plugin versions
2. 📝 Update `k8s/lavalink-deployment.yaml` if updates are found
3. 🔀 Create an automated Pull Request with the changes
4. 💬 Add deployment instructions as a PR comment

### Workflow File

`.github/workflows/lavalink-update.yml`

## Manual Usage

### Check for Updates (Local)

```bash
# Install dependencies
pip install pyyaml requests packaging

# Check for updates
python3 scripts/check_plugin_updates.py --check

# Interactive update
python3 scripts/check_plugin_updates.py --interactive

# Auto-update (use with caution)
python3 scripts/check_plugin_updates.py --update
```

### Trigger Workflow Manually

1. Go to **Actions** tab in GitHub
2. Select **Update Lavalink Plugins** workflow
3. Click **Run workflow**

## What Gets Updated

Currently monitored plugins:

- **YouTube Plugin** (`dev.lavalink.youtube:youtube-plugin`)
  - Repository: https://github.com/lavalink-devs/youtube-source
  - Used for: YouTube music playback with OAuth support

- **LavaSrc Plugin** (`com.github.topi314.lavasrc:lavasrc-plugin`)
  - Repository: https://github.com/topi314/LavaSrc
  - Used for: Additional music sources (Spotify metadata, etc.)

## Pull Request Review Process

When an automated PR is created:

### 1. Review the Changes

Check the PR description for:
- Which plugins are being updated
- Version changes (old → new)
- Links to changelogs

### 2. Test the Updates (Optional)

You can test locally before merging:

```bash
# Checkout the PR branch
gh pr checkout <PR_NUMBER>

# Apply to your cluster
kubectl apply -f k8s/lavalink-deployment.yaml

# Watch Lavalink restart
kubectl logs -f deployment/lavalink

# Test music playback
# Use /play command in Discord
```

### 3. Merge the PR

Once you're satisfied:

1. Click **Merge pull request**
2. The main deployment workflow will automatically:
   - Deploy updated Lavalink configuration
   - Restart Lavalink pod
   - Lavalink will download new plugin versions
   - RotiBot will reconnect automatically

### 4. Verify Deployment

After merge, check the deployment:

```bash
# Check Lavalink logs for plugin loading
kubectl logs deployment/lavalink | grep "Loaded.*plugin"

# Expected output:
# Loaded 'youtube-plugin-X.X.X.jar' (17 classes)
# Loaded 'lavasrc-plugin-X.X.X.jar' (168 classes)

# Test music playback in Discord
```

## Rollback

If something breaks after an update:

### Quick Rollback

```bash
# Revert to previous deployment
kubectl rollout undo deployment/lavalink

# Or revert the Git commit
git revert <commit-hash>
git push origin main
```

### Manual Version Pinning

Edit `k8s/lavalink-deployment.yaml` and specify the old version:

```yaml
lavalink:
  plugins:
    - dependency: "dev.lavalink.youtube:youtube-plugin:1.15.0"  # Pin to old version
      snapshot: false
```

## Troubleshooting

### Plugin Download Fails

**Symptoms**: Lavalink fails to start after update

**Solution**:
1. Check Lavalink logs: `kubectl logs deployment/lavalink`
2. Look for download errors
3. Verify the version exists in Maven repository
4. Rollback if needed

### Breaking Changes

**Symptoms**: Music playback broken after update

**Solution**:
1. Check plugin changelogs for breaking changes
2. Update RotiBot code if API changed
3. Consider pinning to older version temporarily

### Workflow Fails

**Symptoms**: GitHub Actions workflow fails

**Common Causes**:
- Maven repositories unreachable
- Invalid YAML syntax after update
- GitHub token permissions

**Solution**:
1. Check workflow logs in Actions tab
2. Verify `k8s/lavalink-deployment.yaml` syntax
3. Re-run workflow manually

## Configuration

### Change Update Schedule

Edit `.github/workflows/lavalink-update.yml`:

```yaml
on:
  schedule:
    # Run weekly instead of daily
    - cron: '0 2 * * 0'  # Every Sunday at 2 AM
```

### Disable Auto-Updates

Remove or comment out the `schedule` section:

```yaml
on:
  # schedule:
  #   - cron: '0 2 * * *'
  workflow_dispatch:  # Keep manual trigger only
```

### Monitor Different Plugins

Add more plugins to `k8s/lavalink-deployment.yaml`:

```yaml
lavalink:
  plugins:
    - dependency: "dev.lavalink.youtube:youtube-plugin:1.16.0"
      snapshot: false
    - dependency: "com.github.topi314.lavasrc:lavasrc-plugin:4.3.0"
      snapshot: false
    - dependency: "com.github.example:new-plugin:1.0.0"  # New plugin
      snapshot: false
```

The workflow will automatically detect and update all listed plugins.

## Benefits

✅ **Stay secure**: Automatic security patches  
✅ **New features**: Get latest plugin features automatically  
✅ **Bug fixes**: Automatic bug fix updates  
✅ **Zero effort**: Fully automated with PR review safety  
✅ **Traceable**: Git history shows all version changes  
✅ **Reversible**: Easy rollback if issues occur  

## Changelog Location

Plugin changelogs:
- YouTube Plugin: https://github.com/lavalink-devs/youtube-source/releases
- LavaSrc Plugin: https://github.com/topi314/LavaSrc/releases

Always check changelogs before merging automated PRs to catch breaking changes!

---

**Last Updated**: January 22, 2026  
**Maintainer**: @soupa.