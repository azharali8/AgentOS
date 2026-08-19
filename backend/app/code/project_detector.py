"""
Project / Framework Detector for AgentOS Phase 3.

Inspects well-known configuration files found during a repository scan to
determine what technology stack the project uses.  Pure in-memory logic;
decision is based solely on the relative paths of scanned files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.app.code.scanner import FileInfo


@dataclass
class ProjectInfo:
    # Runtime / language-level identifiers
    is_python: bool = False
    is_node: bool = False
    is_go: bool = False
    is_rust: bool = False
    is_java: bool = False

    # Python frameworks
    is_fastapi: bool = False
    is_django: bool = False
    is_flask: bool = False

    # Node frameworks
    is_nextjs: bool = False
    is_react: bool = False
    is_vue: bool = False
    is_angular: bool = False
    is_vite: bool = False

    # Testing
    has_pytest: bool = False
    has_jest: bool = False
    has_unittest: bool = False

    # Containerisation / infra
    has_docker: bool = False
    has_docker_compose: bool = False

    # Database / ORM
    has_alembic: bool = False
    has_sqlalchemy: bool = False

    # CI/CD
    has_github_actions: bool = False

    # Detected config files (relative paths)
    detected_configs: list[str] = field(default_factory=list)

    # Framework summary strings for display
    frameworks: list[str] = field(default_factory=list)


class ProjectDetector:
    """Infer project technology stack from a list of scanned FileInfo objects."""

    def detect(self, files: Sequence[FileInfo]) -> ProjectInfo:
        info = ProjectInfo()
        paths = {fi.relative_path.lower() for fi in files}
        # Also keep a set of basenames for quick lookup
        basenames = {fi.relative_path.lower().split("/")[-1] for fi in files}

        def has_path(substr: str) -> bool:
            return any(substr in p for p in paths)

        def has_base(name: str) -> bool:
            return name in basenames

        # ---- Runtime detection ----
        if has_base("requirements.txt") or has_base("pyproject.toml") or has_base("setup.py") or has_base("setup.cfg"):
            info.is_python = True

        if has_base("package.json"):
            info.is_node = True

        if has_base("go.mod") or has_base("go.sum"):
            info.is_go = True

        if has_base("cargo.toml") or has_base("cargo.lock"):
            info.is_rust = True

        if has_base("pom.xml") or has_base("build.gradle") or has_base("build.gradle.kts"):
            info.is_java = True

        # ---- Python frameworks ----
        if info.is_python:
            # Look for framework-specific imports or config files
            if has_path("fastapi") or has_path("app/main.py") or has_path("app/api"):
                info.is_fastapi = True
            if has_path("django") or has_base("manage.py") or has_base("wsgi.py") or has_base("asgi.py"):
                info.is_django = True
            if has_path("flask") or has_base("app.py"):
                info.is_flask = True

        # ---- Node frameworks ----
        if info.is_node:
            if has_base("next.config.js") or has_base("next.config.ts") or has_path(".next/"):
                info.is_nextjs = True
                info.is_react = True  # Next.js implies React
            elif has_base("vite.config.js") or has_base("vite.config.ts"):
                info.is_vite = True
                # Check if react/vue via config files
                if has_path("src/app") or has_path("src/main.tsx") or has_path("src/main.jsx"):
                    info.is_react = True
            if has_path("angular.json"):
                info.is_angular = True
            if has_path("vue.config") or has_path("src/main.vue"):
                info.is_vue = True

        # ---- Testing ----
        if info.is_python:
            if has_path("test_") or has_path("/tests/") or has_path("conftest.py") or has_base("pytest.ini"):
                info.has_pytest = True
            if has_path("unittest"):
                info.has_unittest = True

        if info.is_node:
            if has_base("jest.config.js") or has_base("jest.config.ts") or has_base("jest.config.json"):
                info.has_jest = True

        # ---- Containerisation ----
        if has_base("dockerfile") or has_path("dockerfile"):
            info.has_docker = True
        if has_base("docker-compose.yml") or has_base("docker-compose.yaml"):
            info.has_docker_compose = True

        # ---- DB / ORM ----
        if has_base("alembic.ini") or has_path("alembic/"):
            info.has_alembic = True
        if has_path("sqlalchemy") or has_path("models.py"):
            info.has_sqlalchemy = True

        # ---- CI/CD ----
        if has_path(".github/workflows"):
            info.has_github_actions = True

        # ---- Collect config file paths for display ----
        config_markers = {
            "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
            "package.json", "package-lock.json", "tsconfig.json",
            "next.config.js", "next.config.ts",
            "vite.config.js", "vite.config.ts",
            "go.mod", "cargo.toml", "pom.xml",
            "dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "alembic.ini", ".github/workflows",
        }
        for fi in files:
            b = fi.relative_path.lower().split("/")[-1]
            if b in config_markers or any(m in fi.relative_path.lower() for m in config_markers):
                info.detected_configs.append(fi.relative_path)

        # ---- Build summary ----
        fw: list[str] = []
        if info.is_fastapi:  fw.append("FastAPI")
        elif info.is_django: fw.append("Django")
        elif info.is_flask:  fw.append("Flask")
        elif info.is_python: fw.append("Python")
        if info.is_nextjs:   fw.append("Next.js")
        elif info.is_react:  fw.append("React")
        elif info.is_vue:    fw.append("Vue")
        elif info.is_angular: fw.append("Angular")
        elif info.is_vite:   fw.append("Vite")
        elif info.is_node:   fw.append("Node.js")
        if info.is_go:       fw.append("Go")
        if info.is_rust:     fw.append("Rust")
        if info.is_java:     fw.append("Java")
        if info.has_docker:  fw.append("Docker")
        if info.has_alembic: fw.append("Alembic")
        info.frameworks = fw

        return info
