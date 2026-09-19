#!/usr/bin/env python3
"""
org.py - organize a folder in place.

Commands:
  ext        Move files into folders by type (images/ ebooks/ docs/ ...).
  chunks     Split files into numbered folders (01/ 02/ ...) of N each.
  date       Group by date, and/or prefix filenames with their date.
  pullup     Move all files from subfolders up to this folder.
  rm-empty   Delete empty subfolders.
  undo       Reverse the last journal in a folder.

Common options:
  -r, --recursive   Also process every subfolder, each on its own.
  --preview         Show what would happen. Don't move anything.
  --backup          Copy this whole folder to a sibling first.
  -v, --verbose     Print each file as it's handled.
  --yes             Skip prompts (for scripting; use with care).
  --force           Allow running on risky system paths.

Files only, unless stated. Never deletes folders except rm-empty.
Every run writes a journal so you can undo with 'org.py undo'.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Group table -- edit this freely. Every extension appears exactly once.
# ---------------------------------------------------------------------------

GROUPS: dict[str, set[str]] = {
    "images": {
        "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp",
        "svg", "heic", "ico", "psd", "raw", "cr2", "nef", "orf", "arw",
    },
    "ebooks": {
        "pdf", "epub", "mobi", "azw", "azw3", "djvu", "fb2",
        "cbz", "cbr", "xps", "oxps",
    },
    "docs": {
        "doc", "docx", "odt", "rtf", "pages",
        "xls", "xlsx", "ods", "numbers",
        "ppt", "pptx", "odp", "key",
        "txt", "md", "markdown", "rst", "tex", "log", "csv", "tsv",
        "html", "htm", "json", "xml", "yml", "yaml", "ini", "cfg", "conf",
        "srt", "sub",
    },
    "code": {
        "py", "js", "ts", "java", "c", "cpp", "cc", "cxx", "h", "hpp",
        "cs", "rb", "go", "rs", "php", "pl", "swift", "kt", "kts",
        "sh", "bash", "ps1", "scala", "erl", "ex", "exs",
    },
    "audio": {
        "mp3", "wav", "flac", "aac", "ogg", "m4a", "wma",
        "alac", "aiff", "opus",
    },
    "video": {
        "mp4", "mkv", "mov", "avi", "wmv", "flv", "webm",
        "mpeg", "mpg", "m4v", "3gp",
    },
    "archives": {
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
        "tgz", "tz", "lz", "lzma",
    },
    "fonts": {"ttf", "otf", "woff", "woff2", "eot"},
    "executables": {"exe", "msi", "bin", "app", "deb", "rpm", "apk"},
    "shortcuts": {"lnk", "url", "desktop"},
}

DOUBLE_EXTS = {"tar.gz", "tar.bz2", "tar.xz"}

EXT_TO_GROUP: dict[str, str] = {}
for _group, _exts in GROUPS.items():
    for _e in _exts:
        EXT_TO_GROUP[_e.lower()] = _group

# ---------------------------------------------------------------------------
# 2. Constants
# ---------------------------------------------------------------------------

GROUP_NAMES = set(GROUPS.keys()) | {"others"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}
JOURNAL_PREFIX = "_org_journal_"
MARKER_FILE = "_org_seen"
TREE_FILE = "tree_date.txt"

RISKY_PATHS = [
    Path("C:/Windows"),
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path("C:/ProgramData"),
]


# ---------------------------------------------------------------------------
# 3. Small helpers
# ---------------------------------------------------------------------------

def script_path() -> Path:
    return Path(__file__).resolve()


def is_risky(path: Path) -> bool:
    p = path.resolve()
    if p.parent == p:
        return True
    for r in RISKY_PATHS:
        try:
            if p == r or r in p.parents:
                return True
        except OSError:
            pass
    try:
        if p == Path.home().resolve():
            return True
    except OSError:
        pass
    return False


def is_group_folder(name: str) -> bool:
    return name in GROUP_NAMES


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS


def should_skip_file(p: Path) -> bool:
    try:
        return p.resolve() == script_path()
    except OSError:
        return False


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    parent, stem, suffix = p.parent, p.stem, p.suffix
    i = 1
    while True:
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def ext_of(p: Path) -> str:
    name = p.name.lower()
    for d in DOUBLE_EXTS:
        if name.endswith("." + d):
            return d
    return p.suffix[1:].lower() if p.suffix else ""


def group_of(p: Path) -> str:
    e = ext_of(p)
    if e in DOUBLE_EXTS:
        return "archives"
    if not e:
        return "others"
    return EXT_TO_GROUP.get(e, "others")


def expand_date_tokens(fmt: str, dt: datetime) -> str:
    q = f"q{(dt.month - 1) // 3 + 1}"
    return (fmt
            .replace("y", str(dt.year))
            .replace("m", f"{dt.month:02d}")
            .replace("d", f"{dt.day:02d}")
            .replace("q", q))


# ---------------------------------------------------------------------------
# 4. Journal
# ---------------------------------------------------------------------------

class Journal:
    def __init__(self, folder: Path):
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.path = folder / f"{JOURNAL_PREFIX}{ts}.jsonl"
        self.entries: list[dict] = []
        self.base = folder

    def move(self, src: Path, dst: Path):
        self.entries.append({
            "t": datetime.now().isoformat(timespec="seconds"),
            "op": "move",
            "src": str(src.relative_to(self.base)),
            "dst": str(dst.relative_to(self.base)),
        })

    def mkdir(self, path: Path):
        self.entries.append({
            "t": datetime.now().isoformat(timespec="seconds"),
            "op": "mkdir",
            "path": str(path.relative_to(self.base)),
        })

    def flush(self):
        if not self.entries:
            return
        with self.path.open("w", encoding="utf-8") as f:
            for e in self.entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


def newest_journal(folder: Path) -> Path | None:
    journals = sorted(folder.glob(f"{JOURNAL_PREFIX}*.jsonl"))
    return journals[-1] if journals else None


# ---------------------------------------------------------------------------
# 5. Prompts and preview printing
# ---------------------------------------------------------------------------

def confirm(msg: str, require_yes: bool = False, auto_yes: bool = False) -> bool:
    if auto_yes:
        return True
    if not sys.stdin.isatty():
        note("No terminal for prompt. Pass --yes to confirm, or --preview to preview.")
        return False
    print()
    if require_yes:
        print(msg)
        print("Type 'yes' to confirm: ", end="", flush=True)
        return sys.stdin.readline().strip() == "yes"
    print(f"{msg} [y/N] ", end="", flush=True)
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def banner_dry():
    print("DRY RUN - nothing will be moved.\n")


def note(msg: str):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# 6. Backup
# ---------------------------------------------------------------------------

def do_backup(folder: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d %H%M%S")
    dest = folder.parent / f"{folder.name} (backup {ts})"
    print(f"Backing up {folder} -> {dest} ...", end=" ", flush=True)
    shutil.copytree(folder, dest)
    print("done")
    return dest


# ---------------------------------------------------------------------------
# 7. First-run marker
# ---------------------------------------------------------------------------

def marker_path(folder: Path) -> Path:
    return folder / MARKER_FILE


def has_seen(folder: Path, command: str) -> bool:
    p = marker_path(folder)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    return command in data


def mark_seen(folder: Path, command: str):
    p = marker_path(folder)
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[command] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 8. Scanning
# ---------------------------------------------------------------------------

def scan_files(folder: Path) -> list[Path]:
    out = []
    for entry in folder.iterdir():
        if entry.is_file() and not should_skip_file(entry):
            out.append(entry)
    return out


def subfolders_for_recursion(folder: Path) -> list[Path]:
    out = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_dir():
            continue
        if should_skip_dir(entry.name):
            continue
        if is_group_folder(entry.name):
            continue
        out.append(entry)
    return out


def all_folders(root: Path, recursive: bool) -> list[Path]:
    if not recursive:
        return [root]
    result = [root]
    for sub in subfolders_for_recursion(root):
        result.extend(all_folders(sub, recursive=True))
    return result


# ---------------------------------------------------------------------------
# 9. ext command
# ---------------------------------------------------------------------------

def cmd_ext_one(folder: Path, dry: bool, verbose: bool,
                auto_yes: bool, journal: Journal) -> int:
    files = scan_files(folder)
    if not files:
        return 0

    plan: dict[str, list[Path]] = {}
    for f in files:
        plan.setdefault(group_of(f), []).append(f)

    if dry:
        print(f"[dry] {folder}")
        for g in sorted(plan):
            names = "  ".join(p.name for p in plan[g][:8])
            more = "" if len(plan[g]) <= 8 else f"  (+{len(plan[g]) - 8} more)"
            print(f"  {g}/  ({len(plan[g])})  {names}{more}")
        return len(files)

    total = sum(len(v) for v in plan.values())
    if not confirm(f"Move {total} files in {folder} into {len(plan)} folders?",
                   auto_yes=auto_yes):
        print("Aborted.")
        return 0

    moved = 0
    for g in sorted(plan):
        gdir = folder / g
        if not gdir.exists():
            gdir.mkdir()
            journal.mkdir(gdir)
        for f in plan[g]:
            dst = unique_path(gdir / f.name)
            if verbose:
                print(f"  {f.name} -> {g}/{dst.name}")
            shutil.move(str(f), str(dst))
            journal.move(f, dst)
            moved += 1
    return moved


def cmd_ext(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)

    if args.backup and not args.preview:
        do_backup(folder)

    folders = all_folders(folder, args.recursive)
    total = 0
    for fd in folders:
        journal = Journal(fd)
        if not args.preview:
            print(f"Organizing {fd} by type")
        total += cmd_ext_one(fd, args.preview, args.verbose, args.yes, journal)
        journal.flush()
    if not args.preview:
        print(f"\nMoved {total} files.")


# ---------------------------------------------------------------------------
# 10. chunks command
# ---------------------------------------------------------------------------

def sort_key(p: Path, by: str):
    st = p.stat()
    if by == "created":
        return getattr(st, "st_birthtime", st.st_mtime)
    if by == "mod":
        return st.st_mtime
    return p.name.lower()


def cmd_chunks_one(folder: Path, size: int, sort_by: str,
                   dry: bool, verbose: bool, auto_yes: bool,
                   journal: Journal, dirs_mode: bool = False,
                   name_regex: str = r"^\d{4}-\d{2}-\d{2}$") -> int:
    if dirs_mode:
        import re as _re
        pat = _re.compile(name_regex)
        items = [d for d in folder.iterdir()
                 if d.is_dir() and pat.match(d.name)]
        if sort_by == "name":
            items.sort(key=lambda p: p.name.lower())
        else:
            items.sort(key=lambda p: sort_key(p, sort_by))
    else:
        items = scan_files(folder)
        items.sort(key=lambda p: sort_key(p, sort_by))

    if not items:
        return 0

    existing = [int(d.name) for d in folder.iterdir()
                if d.is_dir() and d.name.isdigit()]
    start = (max(existing) + 1) if existing else 1

    buckets: dict[int, list[Path]] = {}
    for i, f in enumerate(items):
        b = start + i // size
        buckets.setdefault(b, []).append(f)

    width = max(2, len(str(max(buckets))))
    kind = "folders" if dirs_mode else "files"
    if dry:
        print(f"[dry] {folder}: {len(items)} {kind} -> {len(buckets)} buckets")
        for b in sorted(buckets):
            names = "  ".join(p.name for p in buckets[b][:8])
            more = "" if len(buckets[b]) <= 8 else f"  (+{len(buckets[b]) - 8} more)"
            print(f"  {str(b).zfill(width)}/  ({len(buckets[b])})  {names}{more}")
        return len(items)

    if not confirm(f"Split {len(items)} {kind} in {folder} into {len(buckets)} folders?",
                   auto_yes=auto_yes):
        print("Aborted.")
        return 0

    moved = 0
    for b in sorted(buckets):
        bdir = folder / str(b).zfill(width)
        if not bdir.exists():
            bdir.mkdir()
            journal.mkdir(bdir)
        for f in buckets[b]:
            dst = unique_path(bdir / f.name)
            if verbose:
                print(f"  {f.name} -> {bdir.name}/")
            shutil.move(str(f), str(dst))
            journal.move(f, dst)
            moved += 1
    return moved

def cmd_chunks(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)
    if args.backup and not args.preview:
        do_backup(folder)
    folders = all_folders(folder, args.recursive)
    total = 0
    for fd in folders:
        journal = Journal(fd)
        if not args.preview:
            print(f"Chunking {fd}")
        total += cmd_chunks_one(fd, args.size, args.sort, args.preview,
                                args.verbose, args.yes, journal,
                                dirs_mode=getattr(args, "dirs", False),
                                name_regex=getattr(args, "name_regex",
                                                   r"^\d{4}-\d{2}-\d{2}$"))
        journal.flush()
    if not args.preview:
        print(f"\nMoved {total} items.")

NAME_DATE_PATTERNS = {
    "y-m-d": r"(\d{4})[-._]?(\d{2})[-._]?(\d{2})",
    "y-m":   r"(\d{4})[-._]?(\d{2})",
    "y":     r"(\d{4})",
}


def parse_name_date(name: str, fmt: str) -> datetime | None:
    if fmt == "auto":
        for f in ("y-m-d", "y-m", "y"):
            r = parse_name_date(name, f)
            if r:
                return r
        return None
    pat = NAME_DATE_PATTERNS.get(fmt)
    if not pat:
        return None
    m = re.search(pat, name)
    if not m:
        return None
    try:
        y = int(m.group(1))
        mo = int(m.group(2)) if m.lastindex and m.lastindex >= 2 else 1
        d = int(m.group(3)) if m.lastindex and m.lastindex >= 3 else 1
        return datetime(y, mo, d)
    except Exception:
        return None


def file_date(p: Path, by: str, name_fmt: str) -> datetime | None:
    if by == "title":
        return parse_name_date(p.name, name_fmt)
    st = p.stat()
    if by == "mod":
        return datetime.fromtimestamp(st.st_mtime)
    ts = getattr(st, "st_birthtime", st.st_mtime)
    return datetime.fromtimestamp(ts)


def cmd_date_one(folder: Path, args, journal: Journal) -> int:
    files = scan_files(folder)
    if not files:
        return 0

    plan_rename: list[tuple[Path, Path]] = []
    plan_move: list[tuple[Path, str]] = []

    for f in files:
        dt = file_date(f, args.by, args.name_date)
        if not dt:
            continue
        new_path = f
        if args.prefix:
            prefix = dt.strftime("%Y-%m-%d")
            if not f.name.startswith(prefix):
                new_name = f"{prefix} {f.name}"
                new_path = unique_path(folder / new_name)
                plan_rename.append((f, new_path))
        if args.into:
            sub = expand_date_tokens(args.into, dt)
            plan_move.append((new_path, sub))

    if args.preview:
        print(f"[dry] {folder}")
        for src, dst in plan_rename:
            print(f"  rename  {src.name}  ->  {dst.name}")
        for src, sub in plan_move:
            print(f"  move    {src.name}  ->  {sub}/")
        no_date = [f for f in files if not file_date(f, args.by, args.name_date)]
        for f in no_date[:10]:
            print(f"  skip    {f.name}  (no date found)")
        return len(plan_rename) + len(plan_move)

    if not (plan_rename or plan_move):
        return 0
    summary = []
    if plan_rename:
        summary.append(f"rename {len(plan_rename)}")
    if plan_move:
        summary.append(f"move {len(plan_move)}")
    if not confirm(f"In {folder}: " + ", ".join(summary) + "?", auto_yes=args.yes):
        print("Aborted.")
        return 0

    n = 0
    for src, dst in plan_rename:
        if args.verbose:
            print(f"  rename {src.name} -> {dst.name}")
        src.rename(dst)
        journal.move(src, dst)
        n += 1
    for src, sub in plan_move:
        sdir = folder / sub
        if not sdir.exists():
            sdir.mkdir(parents=True)
            journal.mkdir(sdir)
        dst = unique_path(sdir / src.name)
        if args.verbose:
            print(f"  move {src.name} -> {sub}/")
        shutil.move(str(src), str(dst))
        journal.move(src, dst)
        n += 1
    return n


def cmd_date(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)
    if not (args.prefix or args.into):
        note("Nothing to do: pass --prefix and/or --into.")
        return
    if args.backup and not args.preview:
        do_backup(folder)
    folders = all_folders(folder, args.recursive)
    total = 0
    for fd in folders:
        journal = Journal(fd)
        if not args.preview:
            print(f"Dating {fd}")
        total += cmd_date_one(fd, args, journal)
        journal.flush()
    if not args.preview:
        print(f"\nHandled {total} files.")


# ---------------------------------------------------------------------------
# 12. pullup command
# ---------------------------------------------------------------------------

def write_tree(folder: Path):
    target = folder / TREE_FILE
    if target.exists():
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        target = folder / f"tree_date_{ts}.txt"

    lines = [f"{folder}  ({datetime.now().isoformat(timespec='seconds')})"]

    def walk(d: Path, prefix: str):
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for i, e in enumerate(entries):
            last = (i == len(entries) - 1)
            branch = "└── " if last else "├── "
            lines.append(f"{prefix}{branch}{e.name}{'/' if e.is_dir() else ''}")
            if e.is_dir():
                walk(e, prefix + ("    " if last else "│   "))

    walk(folder, "")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target.name}")


def cmd_pullup(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)

    if not args.preview and not has_seen(folder, "pullup") and not args.yes:
        note("First run here. Run 'org.py pullup --preview' first,")
        note("or pass --yes to skip this check.")
        return

    if args.backup and not args.preview:
        do_backup(folder)

    to_move: list[Path] = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        r = Path(root).resolve()
        if r == folder:
            continue
        for f in files:
            p = Path(root) / f
            if should_skip_file(p):
                continue
            to_move.append(p)

    if args.preview:
        banner_dry()
        print(f"Would move {len(to_move)} files up to {folder}:")
        for p in to_move[:20]:
            print(f"  {p.relative_to(folder)}  ->  {p.name}")
        if len(to_move) > 20:
            print(f"  ... (+{len(to_move) - 20} more)")
        print("\nSubfolders would be left in place.")
        mark_seen(folder, "pullup")
        return

    if not to_move:
        print("Nothing to pull up.")
        return

    print(f"About to move {len(to_move)} files up to {folder}.")
    print("A journal will be written. Undo with 'org.py undo'.")
    if not confirm("Proceed?", auto_yes=args.yes):
        print("Aborted.")
        return

    write_tree(folder)
    journal = Journal(folder)
    moved = 0
    for p in to_move:
        dst = unique_path(folder / p.name)
        if args.verbose:
            print(f"  {p.relative_to(folder)}  ->  {dst.name}")
        shutil.move(str(p), str(dst))
        journal.move(p, dst)
        moved += 1
    journal.flush()
    mark_seen(folder, "pullup")
    print(f"Moved {moved} files. Journal: {journal.path.name}")


# ---------------------------------------------------------------------------
# 13. rm-empty command
# ---------------------------------------------------------------------------

def cmd_rm_empty(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)

    if not args.preview and not has_seen(folder, "rm-empty") and not args.yes:
        note("First run here. Run 'org.py rm-empty --preview' first,")
        note("or pass --yes to skip this check.")
        return

    empties: list[Path] = []
    for root, dirs, files in os.walk(folder, topdown=False):
        r = Path(root)
        if r == folder:
            continue
        if should_skip_dir(r.name):
            continue
        try:
            if not any(r.iterdir()):
                empties.append(r)
        except OSError:
            pass

    if args.preview:
        banner_dry()
        print(f"Would delete {len(empties)} empty folders:")
        for e in empties:
            print(f"  {e.relative_to(folder)}/")
        mark_seen(folder, "rm-empty")
        return

    if not empties:
        print("No empty folders.")
        return

    print(f"About to delete {len(empties)} empty folders:")
    for e in empties:
        print(f"  {e.relative_to(folder)}/")
    print("This cannot be undone by 'org.py undo' (folders are not journalled).")
    if not confirm("", require_yes=True, auto_yes=args.yes):
        print("Aborted.")
        return

    for e in empties:
        try:
            e.rmdir()
        except OSError as ex:
            note(f"Could not remove {e}: {ex}")
    mark_seen(folder, "rm-empty")
    print(f"Deleted {len(empties)} folders.")


# ---------------------------------------------------------------------------
# 14. undo command
# ---------------------------------------------------------------------------

def cmd_undo(args):
    folder = Path(args.path).resolve()
    check_risky(folder, args.force)
    j = newest_journal(folder)
    if not j:
        note(f"No journal in {folder}.")
        sys.exit(1)

    entries = [json.loads(line) for line in j.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not entries:
        note("Journal is empty.")
        return

    print(f"Undoing {len(entries)} operations from {j.name}")
    if not confirm("Proceed?", auto_yes=args.yes):
        print("Aborted.")
        return

    for e in reversed(entries):
        try:
            if e["op"] == "move":
                src = folder / e["src"]
                dst = folder / e["dst"]
                if dst.exists():
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    if args.verbose:
                        print(f"  back: {e['dst']} -> {e['src']}")
            elif e["op"] == "mkdir":
                p = folder / e["path"]
                if p.exists() and not any(p.iterdir()):
                    p.rmdir()
        except Exception as ex:
            note(f"Undo failed for {e}: {ex}")

    j.unlink()
    print("Undone.")


# ---------------------------------------------------------------------------
# 15. Path safety
# ---------------------------------------------------------------------------

def check_risky(folder: Path, force: bool):
    if not folder.exists():
        note(f"Folder does not exist: {folder}")
        sys.exit(2)
    if not folder.is_dir():
        note(f"Not a folder: {folder}")
        sys.exit(2)
    if is_risky(folder) and not force:
        note(f"Refusing to run in {folder} (system path or home root).")
        note("Pass --force to override.")
        sys.exit(3)


# ---------------------------------------------------------------------------
# 16. argparse
# ---------------------------------------------------------------------------

def add_common(p):
    p.add_argument("path", nargs="?", default=".", help="folder to organize (default: cwd)")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="also process every subfolder, each on its own")
    p.add_argument("--preview", action="store_true",
                   help="show what would happen; move nothing")
    p.add_argument("--backup", action="store_true",
                   help="copy the whole folder to a sibling first")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print each file as it's handled")
    p.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--force", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="org.py",
        description="Organize a folder in place. Files only, unless stated.",
        epilog="See each command's --help for details.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("ext", help="move files into type folders")
    add_common(pe)
    pe.set_defaults(func=cmd_ext)

    pc = sub.add_parser("chunks", help="split files (or folders) into numbered folders")
    add_common(pc)
    pc.add_argument("--size", type=int, default=10, help="items per folder (default: 10)")
    pc.add_argument("--sort", choices=["created", "mod", "name"], default="created",
                    help="order items before chunking (default: created)")
    pc.add_argument("--dirs", action="store_true",
                    help="chunk subfolders instead of files")
    pc.add_argument("--name-regex", default=r"^\d{4}-\d{2}-\d{2}$",
                    help="only chunk folders matching this regex (default: YYYY-MM-DD)")
    pc.set_defaults(func=cmd_chunks)

    pd = sub.add_parser("date", help="group by date and/or prefix filenames")
    add_common(pd)
    pd.add_argument("--prefix", action="store_true",
                    help="rename files to start with their date")
    pd.add_argument("--into", metavar="FMT",
                    help="move into date folders: y | y/m | y/q | y-m-d")
    pd.add_argument("--by", choices=["created", "mod", "title"], default="created",
                    help="which date to use (default: created)")
    pd.add_argument("--name-date", choices=["y-m-d", "y-m", "y", "auto"], default="auto",
                    help="date format inside filename, for --by title (default: auto)")
    pd.set_defaults(func=cmd_date)

    pp = sub.add_parser("pullup", help="move all files from subfolders up to this folder")
    add_common(pp)
    pp.set_defaults(func=cmd_pullup)

    pr = sub.add_parser("rm-empty", help="delete empty subfolders")
    add_common(pr)
    pr.set_defaults(func=cmd_rm_empty)

    pu = sub.add_parser("undo", help="reverse the last journal in a folder")
    add_common(pu)
    pu.set_defaults(func=cmd_undo)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
