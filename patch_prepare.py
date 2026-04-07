import re

with open('trigger_workflow/git_client.py', 'r') as f:
    content = f.read()

content = content.replace("ensure_git_branch(local_path, branch, base_branch=config.main_branch)", "ensure_git_branch(local_path, branch)")

old_merge = """    # Auto-merge from base branch as requested for phases after Tiferet
    parent_issue = extract_parent_issue(str(issue_data.get("body") or "")) if issue_data else None
    base_branch = f"{config.issue_branch_prefix}{parent_issue}" if parent_issue else config.main_branch

    if branch != base_branch:"""

new_merge = """    # Auto-merge from base branch as requested for phases after Tiferet
    parent_issue = extract_parent_issue(str(issue_data.get("body") or "")) if issue_data else None
    base_branch = f"{config.issue_branch_prefix}{parent_issue}" if parent_issue else None

    if base_branch and branch != base_branch:"""

content = content.replace(old_merge, new_merge)

old_tiferet = """    # Ensure the parent branch exists, creating it from main if necessary
    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)"""
new_tiferet = """    # Ensure the parent branch exists
    ensure_git_branch(local_path, parent_branch)"""

content = content.replace(old_tiferet, new_tiferet)

old_tiferet2 = """    # Return to the parent branch to finish Tiferet phase
    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)"""
new_tiferet2 = """    # Return to the parent branch to finish Tiferet phase
    ensure_git_branch(local_path, parent_branch)"""

content = content.replace(old_tiferet2, new_tiferet2)

with open('trigger_workflow/git_client.py', 'w') as f:
    f.write(content)
