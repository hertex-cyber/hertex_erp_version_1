#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {
    ".git", ".venv", "__pycache__", "node_modules", "test-results",
    "playwright-report", "tests", "backend/scripts",
}
QUOTED_VALUE = re.compile(r"[:=]\s*['\"][^'\"]{4,}['\"]")
TOKEN_VALUE = re.compile(r"\b(?:sk_live|AKIA|ghp_|xoxb|secret-)[\w-]{8,}", re.IGNORECASE)


def secret_keys() -> set[str]:
    from app.modules.settings.registry import ALIASES, secret_descriptors

    keys = {descriptor.key for descriptor in secret_descriptors()}
    keys.update(ALIASES)
    return keys


def scan_text(text: str, source: str = "<text>") -> list[str]:
    keys = sorted(secret_keys(), key=len, reverse=True)
    lines = text.splitlines()
    findings: list[str] = []
    for index, line in enumerate(lines):
        for key in keys:
            if not re.search(rf"['\"]{re.escape(key)}['\"]", line):
                continue
            if source.endswith("registry.py"):
                continue
            context = "\n".join(lines[index : index + 3])
            has_token = bool(TOKEN_VALUE.search(context))
            has_quoted_value = bool(QUOTED_VALUE.search(context.replace(key, "")))
            if has_token or has_quoted_value:
                findings.append(f"{source}:{index + 1}: secret key '{key}' in value-bearing context")
            break
    return findings


def source_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        candidates = ROOT.rglob("*")
    else:
        candidates = [ROOT / name for name in result.stdout.splitlines()]
    files: list[Path] = []
    for path in candidates:
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_PARTS for part in relative.split("/")):
            continue
        if path.is_file():
            files.append(path)
    return files


def scan_repo() -> list[str]:
    findings: list[str] = []
    for path in source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(text, path.relative_to(ROOT).as_posix()))
    return findings


def main() -> int:
    findings = scan_repo()
    if findings:
        print("Potential settings secret leaks found:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("Settings secret leak scan OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
