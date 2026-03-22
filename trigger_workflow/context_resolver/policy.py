from __future__ import annotations

import subprocess
import uuid


def detect_local_repo_name() -> str:
    """
    Attempts to detect the owner/repo name from the local git remote.
    
    This ensures the swarm can be run from within any target repository without 
    manual repository name input.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            url = result.stdout.strip()
            # Handles both SSH (git@github.com:owner/repo.git) 
            # and HTTPS (https://github.com/owner/repo.git) formats.
            if url.endswith(".git"):
                url = url[:-4]
            
            if "github.com" in url:
                url = url.split("github.com")[-1]
            if url.startswith(":") or url.startswith("/"):
                url = url[1:]
            
            parts = url.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
    except Exception:
        pass
    return ""