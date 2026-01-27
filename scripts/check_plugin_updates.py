#!/usr/bin/env python3
"""
Check for Lavalink plugin updates and optionally update the configuration without running the automation.

Usage:
    python3 check_plugin_updates.py --check           # Just check for updates
    python3 check_plugin_updates.py --update          # Update the config file
    python3 check_plugin_updates.py --interactive     # Interactive mode
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from packaging import version


class PluginUpdater:
    MAVEN_CENTRAL_SEARCH = "https://search.maven.org/solrsearch/select"
    LAVALINK_MAVEN = "https://maven.lavalink.dev/releases"
    
    def __init__(self, config_path: str = "k8s/lavalink-deployment.yaml"):
        self.config_path = Path(config_path)
        
    def get_latest_version(self, group_id: str, artifact_id: str) -> Optional[str]:
        """Fetch the latest version of a Maven artifact."""
        # Try Maven Central first
        try:
            params = {
                'q': f'g:{group_id} AND a:{artifact_id}',
                'rows': 1,
                'wt': 'json'
            }
            resp = requests.get(self.MAVEN_CENTRAL_SEARCH, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data['response']['numFound'] > 0:
                return data['response']['docs'][0]['latestVersion']
        except Exception as e:
            print(f"  ⚠️  Maven Central lookup failed: {e}", file=sys.stderr)
        
        # Fallback to Lavalink Maven
        try:
            maven_path = group_id.replace('.', '/')
            url = f"{self.LAVALINK_MAVEN}/{maven_path}/{artifact_id}/maven-metadata.xml"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            
            # Parse XML for version
            latest_match = re.search(r'<latest>([^<]+)</latest>', resp.text)
            if latest_match:
                return latest_match.group(1)
            
            release_match = re.search(r'<release>([^<]+)</release>', resp.text)
            if release_match:
                return release_match.group(1)
        except Exception as e:
            print(f"  ⚠️  Lavalink Maven lookup failed: {e}", file=sys.stderr)
        
        return None
    
    def parse_dependency(self, dep_string: str) -> Optional[Tuple[str, str, str]]:
        """Parse a dependency string like 'group:artifact:version'."""
        parts = dep_string.split(':')
        if len(parts) != 3:
            return None
        return tuple(parts)
    
    def check_updates(self) -> List[Dict[str, str]]:
        """Check for available plugin updates."""
        if not self.config_path.exists():
            print(f"❌ Configuration file not found: {self.config_path}")
            sys.exit(1)
        
        # Read and parse config
        with open(self.config_path, 'r') as f:
            content = f.read()
        
        # Extract YAML from ConfigMap
        config_start = content.find('application.yml: |')
        if config_start == -1:
            print("❌ Could not find application.yml in ConfigMap")
            sys.exit(1)
        
        yaml_content = content[config_start + len('application.yml: |'):].split('---')[0]
        config = yaml.safe_load(yaml_content)
        
        plugins = config.get('lavalink', {}).get('plugins', [])
        updates = []
        
        print("🔍 Checking for plugin updates...\n")
        
        for plugin in plugins:
            dependency = plugin.get('dependency', '')
            if not dependency:
                continue
            
            parsed = self.parse_dependency(dependency)
            if not parsed:
                print(f"⚠️  Skipping invalid dependency: {dependency}")
                continue
            
            group_id, artifact_id, current_version = parsed
            print(f"📦 {artifact_id}")
            print(f"   Current: {current_version}")
            
            # Fetch latest version
            latest_version = self.get_latest_version(group_id, artifact_id)
            
            if not latest_version:
                print(f"   ❌ Could not fetch latest version\n")
                continue
            
            print(f"   Latest:  {latest_version}")
            
            # Compare versions
            try:
                if version.parse(latest_version) > version.parse(current_version):
                    print(f"   ✨ Update available!\n")
                    updates.append({
                        'artifact': artifact_id,
                        'group': group_id,
                        'current': current_version,
                        'latest': latest_version,
                        'old_dependency': dependency,
                        'new_dependency': f"{group_id}:{artifact_id}:{latest_version}"
                    })
                else:
                    print(f"   ✅ Up to date\n")
            except Exception as e:
                print(f"   ⚠️  Version comparison failed: {e}\n")
        
        return updates
    
    def apply_updates(self, updates: List[Dict[str, str]]) -> None:
        """Apply updates to the configuration file."""
        with open(self.config_path, 'r') as f:
            content = f.read()
        
        for update in updates:
            old_dep = update['old_dependency']
            new_dep = update['new_dependency']
            
            content = content.replace(old_dep, new_dep)
            print(f"✅ Updated {update['artifact']}: {update['current']} → {update['latest']}")
        
        # Write back
        with open(self.config_path, 'w') as f:
            f.write(content)
        
        print(f"\n💾 Configuration saved to {self.config_path}")


def main():
    parser = argparse.ArgumentParser(description="Check and update Lavalink plugin versions")
    parser.add_argument('--check', action='store_true', help="Check for updates only")
    parser.add_argument('--update', action='store_true', help="Automatically apply updates")
    parser.add_argument('--interactive', action='store_true', help="Interactive mode")
    parser.add_argument('--config', default='k8s/lavalink-deployment.yaml',
                       help="Path to Lavalink deployment config")
    
    args = parser.parse_args()
    
    updater = PluginUpdater(args.config)
    updates = updater.check_updates()
    
    if not updates:
        print("🎉 All plugins are up to date!")
        return 0
    
    print(f"\n📊 Summary: {len(updates)} update(s) available")
    
    if args.check:
        # Just list updates
        return 0
    
    if args.update:
        # Auto-apply
        updater.apply_updates(updates)
        return 0
    
    if args.interactive:
        # Ask user
        print("\nApply these updates? (y/n): ", end='')
        response = input().strip().lower()
        
        if response == 'y':
            updater.apply_updates(updates)
            return 0
        else:
            print("❌ Updates cancelled")
            return 1
    
    # Default: just show what would be updated
    print("\nTo apply updates, run with --update or --interactive")
    return 0


if __name__ == '__main__':
    sys.exit(main())