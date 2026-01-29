#!/usr/bin/env python3
"""
JSON Publisher for GitHub Actions
Publishes JSON from stdin to Git, GitHub Releases, or GitHub Pages
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import urllib.request
import urllib.error


class JSONPublisher:
    def __init__(self, json_data: Dict[str, Any], args: argparse.Namespace):
        self.json_data = json_data
        self.args = args
        self.github_token = args.github_token or os.environ.get('GITHUB_TOKEN')
        self.repo = args.repo or os.environ.get('GITHUB_REPOSITORY')

    def publish(self):
        """Main publishing logic based on mode"""
        mode = self.args.mode

        if mode == 'git':
            return self.publish_to_git()
        elif mode == 'release':
            return self.publish_to_release()
        elif mode == 'pages':
            return self.publish_to_pages()
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def publish_to_git(self):
        """Publish JSON as a file to git repository"""
        output_path = self.args.output or 'report.json'

        print(f"Publishing JSON to git file: {output_path}")

        # Write JSON to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(self.json_data, f, indent=2)

        print(f"✓ JSON written to {output_path}")

        # Git operations if requested
        if self.args.commit:
            commit_message = self.args.commit_message or f"Update {output_path}"

            # Configure git if needed
            self._configure_git()

            # Git add, commit, push
            subprocess.run(['git', 'add', output_path], check=True)

            # Check if there are changes to commit
            result = subprocess.run(
                ['git', 'diff', '--cached', '--quiet'],
                capture_output=True
            )

            if result.returncode != 0:  # There are changes
                subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                print(f"✓ Committed changes: {commit_message}")

                if self.args.push:
                    branch = self.args.branch or self._get_current_branch()
                    self._push_with_retry(branch)
                    print(f"✓ Pushed to {branch}")
            else:
                print("⊘ No changes to commit")

        return output_path

    def publish_to_release(self):
        """Publish JSON as a GitHub Release artifact"""
        if not self.github_token:
            raise ValueError("GitHub token is required for release mode")

        if not self.repo:
            raise ValueError("Repository is required for release mode")

        tag = self.args.tag
        if not tag:
            raise ValueError("Release tag is required (--tag)")

        filename = self.args.output or 'report.json'

        print(f"Publishing JSON to GitHub Release: {tag}")

        # Write JSON to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.json_data, f, indent=2)
            temp_path = f.name

        try:
            # Check if release exists
            release_id = self._get_or_create_release(tag)

            # Upload asset
            self._upload_release_asset(release_id, temp_path, filename)

            print(f"✓ Uploaded {filename} to release {tag}")
            return f"https://github.com/{self.repo}/releases/tag/{tag}"

        finally:
            os.unlink(temp_path)

    def publish_to_pages(self):
        """Publish JSON as HTML to GitHub Pages"""
        output_path = self.args.output or 'index.html'

        print(f"Publishing JSON to GitHub Pages: {output_path}")

        # Generate HTML from JSON
        html_content = self._generate_html(self.json_data)

        # Write HTML to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(html_content)

        print(f"✓ HTML generated at {output_path}")

        # Also save the raw JSON
        json_path = output_path.replace('.html', '.json')
        with open(json_path, 'w') as f:
            json.dump(self.json_data, f, indent=2)

        print(f"✓ JSON saved at {json_path}")

        # Git operations if requested
        if self.args.commit:
            commit_message = self.args.commit_message or f"Update GitHub Pages: {output_path}"

            self._configure_git()

            subprocess.run(['git', 'add', output_path, json_path], check=True)

            # Check if there are changes to commit
            result = subprocess.run(
                ['git', 'diff', '--cached', '--quiet'],
                capture_output=True
            )

            if result.returncode != 0:
                subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                print(f"✓ Committed changes: {commit_message}")

                if self.args.push:
                    branch = self.args.branch or 'gh-pages'
                    self._push_with_retry(branch)
                    print(f"✓ Pushed to {branch}")
            else:
                print("⊘ No changes to commit")

        return output_path

    def _generate_html(self, data: Dict[str, Any]) -> str:
        """Generate HTML from JSON data with default styling"""
        # Use static timestamp when TEST=1 (for snapshots), otherwise use current time
        if os.environ.get('TEST') == '1':
            timestamp = '2025-11-19 18:34:10 UTC'
        else:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')

        # Convert JSON to formatted HTML
        json_html = self._json_to_html(data)
        
        # Generate JSON download link - use relative path in test mode
        if os.environ.get('TEST') == '1' and self.args.output:
            # Use just the basename for snapshots to avoid absolute path differences
            json_link = Path(self.args.output).name.replace('.html', '.json')
        elif self.args.output:
            json_link = self.args.output.replace('.html', '.json')
        else:
            json_link = 'index.json'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JSON Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 3px solid #3498db;
        }}

        .timestamp {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 20px;
        }}

        .json-container {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 20px;
            overflow-x: auto;
        }}

        .json-key {{
            color: #e74c3c;
            font-weight: 600;
        }}

        .json-string {{
            color: #27ae60;
        }}

        .json-number {{
            color: #3498db;
        }}

        .json-boolean {{
            color: #9b59b6;
            font-weight: 600;
        }}

        .json-null {{
            color: #95a5a6;
            font-style: italic;
        }}

        .json-object, .json-array {{
            margin-left: 20px;
        }}

        .json-line {{
            margin: 4px 0;
        }}

        .actions {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
        }}

        .btn {{
            display: inline-block;
            padding: 10px 20px;
            background: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            margin-right: 10px;
        }}

        .btn:hover {{
            background: #2980b9;
        }}

        .raw-json {{
            display: none;
            background: #2c3e50;
            color: #ecf0f1;
            padding: 20px;
            border-radius: 4px;
            margin-top: 20px;
            overflow-x: auto;
        }}

        .raw-json pre {{
            margin: 0;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }}

        .raw-json.show {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>JSON Report</h1>
        <div class="timestamp">Generated: {timestamp}</div>

        <div class="json-container">
            {json_html}
        </div>

        <div class="actions">
            <button class="btn" onclick="toggleRaw()">Toggle Raw JSON</button>
            <button class="btn" onclick="copyToClipboard()">Copy JSON</button>
            <a class="btn" href="{json_link}" download>Download JSON</a>
        </div>

        <div class="raw-json" id="rawJson">
            <pre>{json.dumps(data, indent=2)}</pre>
        </div>
    </div>

    <script>
        function toggleRaw() {{
            document.getElementById('rawJson').classList.toggle('show');
        }}

        function copyToClipboard() {{
            const json = {json.dumps(json.dumps(data))};
            navigator.clipboard.writeText(json).then(() => {{
                alert('JSON copied to clipboard!');
            }});
        }}
    </script>
</body>
</html>"""

        return html

    def _json_to_html(self, obj: Any, indent: int = 0) -> str:
        """Convert JSON object to formatted HTML"""
        if isinstance(obj, dict):
            if not obj:
                return '<span class="json-object">{}</span>'

            lines = ['<div class="json-object">{']
            items = list(obj.items())
            for i, (key, value) in enumerate(items):
                comma = ',' if i < len(items) - 1 else ''
                lines.append(
                    f'<div class="json-line">'
                    f'<span class="json-key">"{key}"</span>: '
                    f'{self._json_to_html(value, indent + 1)}{comma}'
                    f'</div>'
                )
            lines.append('}</div>')
            return ''.join(lines)

        elif isinstance(obj, list):
            if not obj:
                return '<span class="json-array">[]</span>'

            lines = ['<div class="json-array">[']
            for i, item in enumerate(obj):
                comma = ',' if i < len(obj) - 1 else ''
                lines.append(
                    f'<div class="json-line">'
                    f'{self._json_to_html(item, indent + 1)}{comma}'
                    f'</div>'
                )
            lines.append(']</div>')
            return ''.join(lines)

        elif isinstance(obj, str):
            return f'<span class="json-string">"{obj}"</span>'

        elif isinstance(obj, (int, float)):
            return f'<span class="json-number">{obj}</span>'

        elif isinstance(obj, bool):
            return f'<span class="json-boolean">{str(obj).lower()}</span>'

        elif obj is None:
            return '<span class="json-null">null</span>'

        else:
            return f'<span>{str(obj)}</span>'

    def _configure_git(self):
        """Configure git user if not already configured"""
        try:
            subprocess.run(['git', 'config', 'user.name'],
                          check=True, capture_output=True)
        except subprocess.CalledProcessError:
            name = self.args.git_user or 'github-actions[bot]'
            email = self.args.git_email or 'github-actions[bot]@users.noreply.github.com'
            subprocess.run(['git', 'config', 'user.name', name], check=True)
            subprocess.run(['git', 'config', 'user.email', email], check=True)

    def _get_current_branch(self) -> str:
        """Get current git branch"""
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    def _push_with_retry(self, branch: str, max_retries: int = 4):
        """Push to remote with exponential backoff retry"""
        for attempt in range(max_retries):
            try:
                subprocess.run(
                    ['git', 'push', '-u', 'origin', branch],
                    check=True,
                    capture_output=True
                )
                return
            except subprocess.CalledProcessError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Push failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(wait_time)
                else:
                    raise

    def _get_or_create_release(self, tag: str) -> str:
        """Get existing release or create new one"""
        api_url = f"https://api.github.com/repos/{self.repo}/releases/tags/{tag}"

        # Try to get existing release
        try:
            release_data = self._github_api_request(api_url, method='GET')
            return release_data['id']
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Create new release
                print(f"Creating new release: {tag}")
                create_url = f"https://api.github.com/repos/{self.repo}/releases"
                release_data = self._github_api_request(
                    create_url,
                    method='POST',
                    data={
                        'tag_name': tag,
                        'name': tag,
                        'body': f'Release {tag}',
                        'draft': False,
                        'prerelease': False
                    }
                )
                return release_data['id']
            else:
                raise

    def _upload_release_asset(self, release_id: str, file_path: str, filename: str):
        """Upload asset to GitHub Release"""
        upload_url = f"https://uploads.github.com/repos/{self.repo}/releases/{release_id}/assets"

        with open(file_path, 'rb') as f:
            file_data = f.read()

        headers = {
            'Authorization': f'token {self.github_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github.v3+json'
        }

        url = f"{upload_url}?name={filename}"
        request = urllib.request.Request(url, data=file_data, headers=headers, method='POST')

        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"Failed to upload asset: {e.code} {error_body}")

    def _github_api_request(self, url: str, method: str = 'GET', data: Optional[Dict] = None):
        """Make GitHub API request"""
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }

        request_data = json.dumps(data).encode('utf-8') if data else None
        request = urllib.request.Request(url, data=request_data, headers=headers, method=method)

        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(
        description='Publish JSON from stdin to Git, GitHub Releases, or GitHub Pages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Publish to git file
  cat report.json | python publish.py --mode git --output results/report.json --commit --push

  # Publish to GitHub Release
  cat report.json | python publish.py --mode release --tag v1.0.0 --output report.json

  # Publish to GitHub Pages
  cat report.json | python publish.py --mode pages --output index.html --commit --push --branch gh-pages
        """
    )

    # Mode selection
    parser.add_argument(
        '--mode',
        choices=['git', 'release', 'pages'],
        required=True,
        help='Publishing mode: git (file), release (GitHub Release), or pages (GitHub Pages)'
    )

    # Output configuration
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: report.json for git/release, index.html for pages)'
    )

    # Git options
    parser.add_argument(
        '--commit',
        action='store_true',
        help='Commit changes to git'
    )

    parser.add_argument(
        '--push',
        action='store_true',
        help='Push changes to remote (requires --commit)'
    )

    parser.add_argument(
        '--branch',
        help='Git branch to use (default: current branch for git mode, gh-pages for pages mode)'
    )

    parser.add_argument(
        '--commit-message',
        help='Custom commit message'
    )

    parser.add_argument(
        '--git-user',
        help='Git user name (default: github-actions[bot])'
    )

    parser.add_argument(
        '--git-email',
        help='Git user email (default: github-actions[bot]@users.noreply.github.com)'
    )

    # GitHub Release options
    parser.add_argument(
        '--tag',
        help='Release tag (required for release mode)'
    )

    # GitHub configuration
    parser.add_argument(
        '--github-token',
        help='GitHub token (can also use GITHUB_TOKEN env var)'
    )

    parser.add_argument(
        '--repo',
        help='Repository in format owner/repo (can also use GITHUB_REPOSITORY env var)'
    )

    args = parser.parse_args()

    # Read JSON from stdin
    try:
        if sys.stdin.isatty():
            print("Error: No input provided. Please pipe JSON data to stdin.", file=sys.stderr)
            print("Example: cat report.json | python publish.py --mode git", file=sys.stderr)
            sys.exit(1)

        json_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    # Publish
    try:
        publisher = JSONPublisher(json_data, args)
        result = publisher.publish()
        print(f"\n✓ Successfully published!")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
