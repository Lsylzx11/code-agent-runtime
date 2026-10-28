from __future__ import annotations

from pathlib import Path


class WorkspaceError(ValueError):
    pass


def resolve_workspace_path(workspace: Path, user_path: str) -> Path:
    if not isinstance(user_path, str) or not user_path.strip():
        raise WorkspaceError("path must be a non-empty string")
    root = workspace.resolve()
    candidate = Path(user_path)
    if candidate.is_absolute():
        raise WorkspaceError("absolute paths are not allowed")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise WorkspaceError("path escapes the workspace")
    return resolved


def read_file(workspace: Path, path: str, offset: int = 0, limit: int | None = None) -> str:
    target = resolve_workspace_path(workspace, path)
    if not target.is_file():
        raise WorkspaceError(f"not a file: {path}")
    lines = target.read_text(encoding="utf-8").splitlines()
    offset = max(0, int(offset))
    selected = lines[offset:] if limit is None else lines[offset:offset + max(0, int(limit))]
    suffix = "" if len(selected) == len(lines[offset:]) else f"\n... ({len(lines[offset:]) - len(selected)} more lines)"
    return "\n".join(selected) + suffix


def list_files(workspace: Path, path: str = ".", recursive: bool = False) -> str:
    target = resolve_workspace_path(workspace, path)
    if not target.is_dir():
        raise WorkspaceError(f"not a directory: {path}")
    entries = target.rglob("*") if recursive else target.iterdir()
    root = workspace.resolve()
    names = sorted(str(item.resolve().relative_to(root)) for item in entries
                   if item.resolve().is_relative_to(root))
    return "\n".join(names[:500]) + ("\n... (more entries omitted)" if len(names) > 500 else "")


def glob_files(workspace: Path, pattern: str) -> str:
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        raise WorkspaceError("glob pattern escapes the workspace")
    root = workspace.resolve()
    matches = sorted(str(item.resolve().relative_to(root)) for item in root.glob(pattern)
                     if item.resolve().is_relative_to(root))
    return "\n".join(matches[:500]) or "(no matches)"


def write_file(workspace: Path, path: str, content: str) -> str:
    target = resolve_workspace_path(workspace, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Resolve again after creating parents, so a newly traversed symlink cannot escape.
    if target != workspace.resolve() and workspace.resolve() not in target.resolve().parents:
        raise WorkspaceError("path escapes the workspace")
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content.encode('utf-8'))} bytes to {path}"


def edit_file(workspace: Path, path: str, old_text: str, new_text: str) -> str:
    target = resolve_workspace_path(workspace, path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count != 1:
        raise WorkspaceError(f"expected exactly one matching block, found {count}")
    target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"edited {path}"


def grep(workspace: Path, query: str, path: str = ".") -> str:
    if not query:
        raise WorkspaceError("query must not be empty")
    target = resolve_workspace_path(workspace, path)
    files = [target] if target.is_file() else target.rglob("*")
    root = workspace.resolve()
    found: list[str] = []
    for file in files:
        if not file.is_file() or not file.resolve().is_relative_to(root):
            continue
        try:
            for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if query in line:
                    found.append(f"{file.resolve().relative_to(root)}:{number}:{line}")
                    if len(found) >= 500:
                        return "\n".join(found) + "\n... (more matches omitted)"
        except UnicodeDecodeError:
            continue
    return "\n".join(found) or "(no matches)"

