import re

with open('trigger_workflow/git_client.py', 'r') as f:
    content = f.read()

# 1. Update ensure_git_branch signature and body
new_ensure = """def ensure_git_branch(local_path: Path, branch: str, *, base_branch: str | None = None) -> None:
    \"\"\"Switch to the requested branch, creating it from base_branch (or current branch) if it does not exist.\"\"\"
    if base_branch in ("main", "master"):
        raise SystemExit(f"Cannot use '{base_branch}' as base branch.")

    active_branch = current_branch(local_path)
    if active_branch == branch:
        log_info(f"Git branch already active: {branch}")
        return

    if branch_exists(local_path, branch):
        log_info(f"Switching target repository to existing branch '{branch}'")
        git_run_strict(local_path, ["switch", branch], failure_message=f"Failed to switch {local_path} to branch '{branch}'", capture_output=True)
        return

    target_base = base_branch or active_branch

    if target_base in ("main", "master"):
        raise SystemExit(f"Cannot use '{target_base}' as the base branch.")

    def _try_create_branch(target: str) -> bool:
        log_info(f"Branch '{branch}' does not exist; creating it from '{target}'.")
        # Try creating from local base first
        result = git_run(local_path, ["switch", "-c", branch, target], capture_output=True)
        if result.returncode == 0:
            return True
            
        # Fallback to origin/base if local doesn't exist
        log_info(f"Failed to create from local '{target}', trying 'origin/{target}'...")
        git_run(local_path, ["fetch", "origin", target])
        result = git_run(
            local_path, 
            ["switch", "-c", branch, f"origin/{target}"], 
            capture_output=True
        )
        return result.returncode == 0

    if branch == target_base:
        raise SystemExit(f"Base branch '{target_base}' does not exist locally in {local_path}.")

    success = _try_create_branch(target_base)
        
    if not success:
        raise SystemExit(f"Failed to create branch '{branch}' from '{target_base}'.")
    
    log_info(f"Pushing new branch '{branch}' to origin...")
    git_run_strict(local_path, ["push", "-u", "origin", branch], failure_message=f"Failed to push new branch '{branch}'")
"""

content = re.sub(r'def ensure_git_branch\(local_path: Path, branch: str, \*, base_branch: str\) -> None:.*?git_run_strict\(local_path, \["push", "-u", "origin", branch\], failure_message=f"Failed to push new branch \'\{branch\}\'"\)', new_ensure, content, flags=re.DOTALL)

with open('trigger_workflow/git_client.py', 'w') as f:
    f.write(content)
