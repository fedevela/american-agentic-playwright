#!/usr/bin/env python3
"""
Simple todo manager for tracking multi-step tasks.
"""
import json
import sys
from pathlib import Path
from typing import Optional


class TodoManager:
    def __init__(self, state_file: str = "workspace/.sdlc-state.json"):
        self.workspace = Path(__file__).parent.parent
        self.state_file = self.workspace / state_file
        self.data = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    if "todos" in data:
                        return data
            except Exception:
                pass
        return {"todos": [], "current": None}

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.data, f, indent=2)

    def add(self, content: str, status: str = "pending") -> str:
        """Add a new todo item."""
        item = {
            "content": content,
            "status": status,
            "active_form": content,
        }
        self.data["todos"].append(item)
        self._save()
        return f"Added: {content}"

    def list(self) -> list:
        """List all todos."""
        return self.data.get("todos", [])

    def update(self, index: int, status: str) -> str:
        """Update a todo's status."""
        todos = self.data.get("todos", [])
        if 0 <= index < len(todos):
            todos[index]["status"] = status
            self._save()
            return f"Updated: {todos[index]['content']} -> {status}"
        return "Invalid todos index"

    def start(self, index: int) -> str:
        """Mark a todo as in_progress."""
        return self.update(index, "in_progress")

    def complete(self, index: int) -> str:
        """Mark a todo as completed."""
        return self.update(index, "completed")


def main():
    if len(sys.argv) < 2:
        print("Usage: python todos.py [add|list|start|complete] [args...]")
        return

    cmd = sys.argv[1]
    manager = TodoManager()

    if cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: python todos.py add 'content'")
            return
        print(manager.add(sys.argv[2]))
    elif cmd == "list":
        for i, todo in enumerate(manager.list()):
            print(f"[{i}] ({todo['status']}) {todo['content']}")
    elif cmd == "start":
        if len(sys.argv) < 3:
            print("Usage: python todos.py start <index>")
            return
        print(manager.start(int(sys.argv[2])))
    elif cmd == "complete":
        if len(sys.argv) < 3:
            print("Usage: python todos.py complete <index>")
            return
        print(manager.complete(int(sys.argv[2])))
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
