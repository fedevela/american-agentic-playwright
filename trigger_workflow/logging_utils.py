from __future__ import annotations


def log_section(title: str) -> None:
    """Print a visible section divider for the console."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def log_step(step: str) -> None:
    """Print a step marker for the console."""
    print(f"\n[✓] {step}")


def log_info(msg: str) -> None:
    """Print an info message."""
    print(f"    → {msg}")


def log_error(msg: str) -> None:
    """Print an error message."""
    print(f"    ! {msg}")


def log_multiline(title: str, body: str) -> None:
    """Print a titled multi-line block for generated content."""
    print(f"    → {title}:")
    for line in body.splitlines() or [""]:
        print(f"      {line}")
