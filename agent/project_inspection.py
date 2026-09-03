from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from agent.evidence import (
    Evidence,
    PROJECT_FILE,
    evidence_dict,
)
from agent.runtime_context import get_runtime_context


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".terraform",
    ".idea",
    ".vscode",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".ps1",
    ".sql",
    ".tf",
    ".dockerfile",
}

TEXT_NAMES = {
    "Dockerfile",
    "Makefile",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "environment.yml",
    "package.json",
    "README.md",
    "README",
}

MAX_FILE_BYTES = 256_000
MAX_FILES_SCANNED = 500
MAX_SEARCH_HITS = 12


_INDEX_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: dict[str, tuple[float, list[Path]]] = {}


def _index_ttl_seconds() -> float:
    try:
        value = float(
            os.environ.get(
                "OPERATIONS_PROJECT_INDEX_TTL_SECONDS",
                "15",
            )
        )
    except ValueError:
        value = 15.0

    return max(
        0.0,
        min(value, 300.0),
    )


def clear_project_index_cache() -> None:
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE.clear()


def classify_project_file(
    relative: str,
) -> str:
    path = Path(relative)
    parts = path.parts
    name = path.name.lower()
    suffix = path.suffix.lower()

    if (
        "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        return "validation"

    if suffix in {
        ".md",
        ".txt",
    }:
        return "documentation"

    if suffix in {
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".ini",
        ".cfg",
        ".conf",
    }:
        return "configuration"

    return "implementation"


def project_root() -> Path:
    return (
        get_runtime_context()
        .project_root
        .resolve()
    )


def _within_root(
    path: Path,
    root: Path,
) -> bool:
    try:
        path.resolve().relative_to(
            root.resolve()
        )
        return True
    except ValueError:
        return False


def _is_text_candidate(
    path: Path,
) -> bool:
    return (
        path.name in TEXT_NAMES
        or path.suffix.lower()
        in TEXT_SUFFIXES
    )


def _git_project_files(
    root: Path,
) -> list[Path] | None:
    """
    Fast path for Git-managed projects.

    Ask Git for tracked plus non-ignored untracked files instead of
    recursively traversing the filesystem. This is especially important
    on metadata-expensive mounts such as WSL /mnt/c.

    Returns None when Git is unavailable or the directory is not a Git
    work tree, allowing the safe os.walk fallback to take over.
    """

    commands = [
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
        ],
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
        ],
    ]

    relative_paths: list[str] = []

    try:
        for command in commands:
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )

            decoded = completed.stdout.decode(
                "utf-8",
                errors="surrogateescape",
            )

            relative_paths.extend(
                item
                for item in decoded.split("\0")
                if item
            )

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return None

    files: list[Path] = []
    seen: set[str] = set()

    for relative in relative_paths:
        if len(files) >= MAX_FILES_SCANNED:
            break

        if relative in seen:
            continue

        seen.add(relative)

        relative_path = Path(relative)

        if any(
            part in IGNORED_DIRS
            for part in relative_path.parts
        ):
            continue

        path = (
            root
            / relative_path
        )

        if not _is_text_candidate(path):
            continue

        try:
            if (
                not path.is_file()
                or path.is_symlink()
                or path.stat().st_size > MAX_FILE_BYTES
            ):
                continue
        except OSError:
            continue

        files.append(path)

    return files


def _walk_project_files(
    root: Path,
) -> list[Path]:
    """
    Portable fallback for non-Git projects.
    """

    files: list[Path] = []

    for (
        dirpath,
        dirnames,
        filenames,
    ) in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(dirpath)

        allowed_dirs: list[str] = []

        for dirname in dirnames:
            if dirname in IGNORED_DIRS:
                continue

            candidate = (
                current
                / dirname
            )

            if candidate.is_symlink():
                continue

            allowed_dirs.append(dirname)

        dirnames[:] = sorted(
            allowed_dirs
        )

        for filename in sorted(
            filenames
        ):
            if len(files) >= MAX_FILES_SCANNED:
                return files

            path = (
                current
                / filename
            )

            if not _is_text_candidate(path):
                continue

            try:
                if (
                    path.is_symlink()
                    or path.stat().st_size > MAX_FILE_BYTES
                ):
                    continue
            except OSError:
                continue

            files.append(path)

    return files


def _build_project_index_uncached(
    root: Path | None = None,
) -> list[Path]:
    root = (
        root.resolve()
        if root
        else project_root()
    )

    git_files = _git_project_files(
        root
    )

    if git_files is not None:
        return git_files

    return _walk_project_files(
        root
    )



def build_project_index(
    root: Path | None = None,
    refresh: bool = False,
) -> list[Path]:
    root = (
        root.resolve()
        if root
        else project_root()
    )

    ttl = _index_ttl_seconds()
    key = str(root)
    now = time.monotonic()

    if (
        not refresh
        and ttl > 0
    ):
        with _INDEX_CACHE_LOCK:
            cached = _INDEX_CACHE.get(key)

        if cached is not None:
            created_at, files = cached

            if (
                now - created_at
                <= ttl
            ):
                return list(files)

    files = _build_project_index_uncached(
        root
    )

    if ttl > 0:
        with _INDEX_CACHE_LOCK:
            _INDEX_CACHE[key] = (
                time.monotonic(),
                list(files),
            )

    return list(files)


def read_project_file(
    relative_path: str,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    root = project_root()

    path = (
        root
        / relative_path
    ).resolve()

    if not _within_root(
        path,
        root,
    ):
        return {
            "status": "BLOCKED",
            "reason": "path_outside_project",
        }

    if (
        not path.is_file()
        or path.is_symlink()
    ):
        return {
            "status": "NOT_FOUND",
        }

    if not _is_text_candidate(
        path
    ):
        return {
            "status": "BLOCKED",
            "reason": "unsupported_file_type",
        }

    try:
        size = path.stat().st_size
    except OSError:
        return {
            "status": "NOT_FOUND",
        }

    if size > MAX_FILE_BYTES:
        return {
            "status": "BLOCKED",
            "reason": "file_too_large",
        }

    text = path.read_text(
        errors="replace"
    )

    relative = str(
        path.relative_to(root)
    )

    return {
        "status": "OK",
        "path": relative,
        "content": text[:max_chars],
        "truncated": (
            len(text)
            > max_chars
        ),
        "evidence": [
            evidence_dict(
                Evidence(
                    type=PROJECT_FILE,
                    source=relative,
                    detail=(
                        "File read directly "
                        "from the active project."
                    ),
                )
            )
        ],
    }


def inspect_project(
    index: list[Path] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve() if root else project_root()

    files = (
        index
        if index is not None
        else build_project_index(
            root
        )
    )

    relative_files = [
        str(
            path.relative_to(
                root
            )
        )
        for path in files
    ]

    markers = [
        name
        for name in (
            "pyproject.toml",
            "requirements.txt",
            "setup.py",
            "environment.yml",
            "Dockerfile",
            "docker-compose.yml",
            "package.json",
            "README.md",
        )
        if (
            root
            / name
        ).is_file()
    ]

    likely_entrypoints = [
        path
        for path in relative_files
        if (
            Path(path).name
            in {
                "main.py",
                "app.py",
                "cli.py",
                "train.py",
                "run.py",
                "server.py",
            }
            or path.startswith(
                "scripts/"
            )
        )
    ][:20]

    evidence = [
        evidence_dict(
            Evidence(
                type=PROJECT_FILE,
                source=marker,
                detail=(
                    "Detected project marker."
                ),
            )
        )
        for marker in markers
    ]

    return {
        "status": "OK",
        "project_name": root.name,
        "files_scanned": len(files),
        "markers": markers,
        "likely_entrypoints":
            likely_entrypoints,
        "evidence": evidence,
    }


def _query_terms(
    query: str,
) -> list[str]:
    words = re.findall(
        r"[A-Za-z0-9_.-]{3,}",
        query.lower(),
    )

    stopwords = {
        "what",
        "does",
        "this",
        "that",
        "with",
        "from",
        "have",
        "about",
        "project",
        "repo",
        "repository",
        "please",
        "tell",
        "explain",
        "could",
        "would",
        "should",
        "where",
        "which",
        "when",
        "files",
        "file",
        "implement",
        "implements",
        "implemented",
        "implementation",
        "and",
        "the",
        "for",
        "into",
        "are",
    }

    terms: list[str] = []

    for word in words:
        if (
            word not in stopwords
            and word not in terms
        ):
            terms.append(word)

    return terms[:10]


def _implementation_question(
    query: str,
) -> bool:
    lowered = query.lower()

    markers = {
        "implement",
        "implementation",
        "code",
        "source",
        "which file",
        "which files",
        "where is",
        "where are",
    }

    return any(
        marker in lowered
        for marker in markers
    )


def _git_grep_project(
    query: str,
    root: Path,
) -> dict[str, Any] | None:
    """
    Fast search path for Git-managed projects.

    git grep performs repository scanning natively rather than opening
    every file individually through Python. --untracked includes
    non-ignored working-tree files that have not yet been committed.
    """

    terms = _query_terms(query)

    if not terms:
        return {
            "status": "OK",
            "query": query,
            "terms": [],
            "hits": [],
            "evidence": [],
            "search_backend": "git_grep",
        }

    command = [
        "git",
        "-C",
        str(root),
        "grep",
        "-n",
        "-I",
        "--full-name",
        "--untracked",
    ]

    for term in terms:
        command.extend(
            [
                "-e",
                term,
            ]
        )

    command.append("--")

    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None

    # git grep:
    #   0 = matches
    #   1 = valid search, no matches
    #  >1 = error / unsuitable repository
    if completed.returncode == 1:
        return {
            "status": "OK",
            "query": query,
            "terms": terms,
            "hits": [],
            "evidence": [],
            "search_backend": "git_grep",
        }

    if completed.returncode != 0:
        return None

    output = completed.stdout.decode(
        "utf-8",
        errors="replace",
    )

    grouped: dict[
        str,
        dict[str, Any],
    ] = {}

    for raw_line in output.splitlines():
        pieces = raw_line.split(
            ":",
            2,
        )

        if len(pieces) != 3:
            continue

        relative, line_no, content = pieces

        relative_path = Path(
            relative
        )

        if any(
            part in IGNORED_DIRS
            for part in relative_path.parts
        ):
            continue

        path = (
            root
            / relative_path
        )

        if not _is_text_candidate(path):
            continue

        entry = grouped.setdefault(
            relative,
            {
                "path": relative,
                "matched_terms": set(),
                "match_count": 0,
                "lines": [],
            },
        )

        lowered = content.lower()

        for term in terms:
            count = lowered.count(term)

            if count:
                entry[
                    "matched_terms"
                ].add(term)

                entry[
                    "match_count"
                ] += count

        if len(entry["lines"]) < 6:
            entry["lines"].append(
                f"{line_no}: {content.strip()}"
            )

    implementation_intent = (
        _implementation_question(
            query
        )
    )

    hits: list[
        dict[str, Any]
    ] = []

    source_suffixes = {
        ".py",
        ".sh",
        ".ps1",
        ".sql",
        ".tf",
    }

    doc_suffixes = {
        ".md",
        ".txt",
    }

    for relative, entry in grouped.items():
        matched_terms = entry[
            "matched_terms"
        ]

        coverage = len(
            matched_terms
        )

        # Coverage matters much more than raw repetition.
        # Raw counts are capped so large README files cannot dominate
        # simply because they repeat vocabulary many times.
        score = (
            coverage * 30
            + min(
                entry["match_count"],
                10,
            )
            * 2
        )

        filename_lower = (
            relative.lower()
        )

        for term in terms:
            if term in filename_lower:
                score += 20

        suffix = Path(
            relative
        ).suffix.lower()

        if implementation_intent:
            if suffix in source_suffixes:
                # For implementation questions, executable/source files
                # should outrank documentation that merely repeats the
                # same vocabulary.
                score += 55

            elif suffix in doc_suffixes:
                score -= 25

            parts = Path(relative).parts

            # Tests are valuable evidence, but when the user asks where
            # something is implemented, production/source code is normally
            # more authoritative than code that only exercises it.
            if (
                "tests" in parts
                or relative.startswith("test_")
                or Path(relative).name.startswith("test_")
            ):
                score -= 45

        excerpt = "\n".join(
            entry["lines"]
        )

        role = classify_project_file(
            relative
        )

        hits.append(
            {
                "path": relative,
                "role": role,
                "score": score,
                "matched_terms": sorted(
                    matched_terms
                ),
                "excerpt": excerpt,
            }
        )

    hits.sort(
        key=lambda item: (
            -item["score"],
            item["path"],
        )
    )

    hits = hits[
        :MAX_SEARCH_HITS
    ]

    evidence = [
        evidence_dict(
            Evidence(
                type=PROJECT_FILE,
                source=hit["path"],
                role=hit.get("role"),
                detail=(
                    "Matched the user's project question "
                    "through bounded repository search."
                ),
                excerpt=hit[
                    "excerpt"
                ],
            )
        )
        for hit in hits
    ]

    return {
        "status": "OK",
        "query": query,
        "terms": terms,
        "hits": hits,
        "evidence": evidence,
        "search_backend": "git_grep",
    }


def _python_search_project(
    query: str,
    root: Path,
    files: list[Path],
) -> dict[str, Any]:
    """
    Portable fallback for projects that are not managed by Git.
    """

    terms = _query_terms(
        query
    )

    implementation_intent = (
        _implementation_question(
            query
        )
    )

    hits: list[
        dict[str, Any]
    ] = []

    for path in files:
        relative = str(
            path.relative_to(
                root
            )
        )

        try:
            text = path.read_text(
                errors="replace"
            )
        except OSError:
            continue

        lower = text.lower()

        counts = {
            term: lower.count(term)
            for term in terms
        }

        matched_terms = {
            term
            for term, count
            in counts.items()
            if count
        }

        if not matched_terms:
            continue

        score = (
            len(matched_terms) * 30
            + min(
                sum(counts.values()),
                10,
            )
            * 2
        )

        filename_lower = (
            relative.lower()
        )

        for term in terms:
            if term in filename_lower:
                score += 20

        suffix = path.suffix.lower()

        if implementation_intent:
            if suffix in {
                ".py",
                ".sh",
                ".ps1",
                ".sql",
                ".tf",
            }:
                score += 55

            elif suffix in {
                ".md",
                ".txt",
            }:
                score -= 25

            parts = Path(relative).parts

            if (
                "tests" in parts
                or relative.startswith("test_")
                or Path(relative).name.startswith("test_")
            ):
                score -= 45

        positions = [
            lower.find(term)
            for term in matched_terms
            if lower.find(term) >= 0
        ]

        excerpt = ""

        if positions:
            pos = min(positions)

            start = max(
                0,
                pos - 180,
            )

            end = min(
                len(text),
                pos + 520,
            )

            excerpt = (
                text[start:end]
                .strip()
            )

        role = classify_project_file(
            relative
        )

        hits.append(
            {
                "path": relative,
                "role": role,
                "score": score,
                "matched_terms": sorted(
                    matched_terms
                ),
                "excerpt": excerpt,
            }
        )

    hits.sort(
        key=lambda item: (
            -item["score"],
            item["path"],
        )
    )

    hits = hits[
        :MAX_SEARCH_HITS
    ]

    evidence = [
        evidence_dict(
            Evidence(
                type=PROJECT_FILE,
                source=hit["path"],
                role=hit.get("role"),
                detail=(
                    "Matched the user's project question."
                ),
                excerpt=hit[
                    "excerpt"
                ],
            )
        )
        for hit in hits
    ]

    return {
        "status": "OK",
        "query": query,
        "terms": terms,
        "hits": hits,
        "evidence": evidence,
        "search_backend": "python_fallback",
    }


def search_project(
    query: str,
    index: list[Path] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve() if root else project_root()

    git_result = _git_grep_project(
        query,
        root,
    )

    if git_result is not None:
        return git_result

    files = (
        index
        if index is not None
        else build_project_index(
            root
        )
    )

    return _python_search_project(
        query,
        root,
        files,
    )

