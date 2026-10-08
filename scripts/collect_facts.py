#!/usr/bin/env python3
"""Collect verifiable facts about a repository as JSON, for an agent to synthesize AGENTS.md.

Usage:
    python collect_facts.py [ROOT] [--audit] [--brain] [--max-depth N]

Stdlib only. Never writes to the repository. Reads file contents only for
config/manifests; never prints .env values (only key names from *.example files).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
    "target", "vendor", ".next", ".nuxt", ".turbo", ".cache", "coverage", ".idea",
    ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache", "out", "bin", "obj",
    ".gradle", ".terraform", "site-packages",
}

MANIFESTS = {
    "package.json": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "Pipfile": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "composer.json": "php",
    "Gemfile": "ruby",
    "pom.xml": "java-maven",
    "build.gradle": "jvm-gradle",
    "build.gradle.kts": "jvm-gradle",
    "CMakeLists.txt": "c-cpp",
    "mix.exs": "elixir",
    "pubspec.yaml": "dart",
    "deno.json": "deno",
}

LOCKFILES = {
    "package-lock.json": "npm", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn",
    "bun.lockb": "bun", "bun.lock": "bun", "poetry.lock": "poetry", "uv.lock": "uv",
    "Pipfile.lock": "pipenv", "pdm.lock": "pdm", "Cargo.lock": "cargo",
    "go.sum": "go", "composer.lock": "composer", "Gemfile.lock": "bundler",
}

AGENT_DOCS = [
    "AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "GEMINI.md", ".cursorrules",
    ".windsurfrules", ".clinerules", ".github/copilot-instructions.md",
]
AGENT_DOC_DIRS = [".cursor/rules", ".github/instructions", ".claude/skills", ".clinerules"]

TOOL_CONFIGS = [
    # lint / format / types
    ".editorconfig", ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
    ".eslintrc.yml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    "eslint.config.ts", ".prettierrc", ".prettierrc.json", ".prettierrc.js",
    "prettier.config.js", "biome.json", "biome.jsonc", "tsconfig.json", "ruff.toml",
    ".ruff.toml", ".flake8", "setup.cfg", "mypy.ini", ".pylintrc", ".golangci.yml",
    ".golangci.yaml", "rustfmt.toml", ".rustfmt.toml", "clippy.toml", ".rubocop.yml",
    "phpcs.xml", ".stylelintrc", ".stylelintrc.json",
    # tests
    "pytest.ini", "tox.ini", "noxfile.py", "jest.config.js", "jest.config.ts",
    "vitest.config.ts", "vitest.config.js", "playwright.config.ts", "cypress.config.ts",
    "phpunit.xml", ".mocharc.json", "karma.conf.js",
    # hooks / commits
    ".pre-commit-config.yaml", ".husky", "lefthook.yml", "commitlint.config.js",
    ".commitlintrc.json", ".lintstagedrc",
    # ui
    "tailwind.config.js", "tailwind.config.ts", "postcss.config.js", "components.json",
    # monorepo
    "pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "go.work",
    "rush.json",
    # runtime / env
    ".nvmrc", ".node-version", ".python-version", ".tool-versions", ".ruby-version",
    "rust-toolchain.toml", "rust-toolchain", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yaml", "compose.yml", "devcontainer.json",
    ".devcontainer",
    # task runners
    "Makefile", "justfile", "Justfile", "Taskfile.yml", "Taskfile.yaml",
]

CI_GLOBS = [
    ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
    ".circleci/config.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml",
    "Jenkinsfile", ".buildkite/pipeline.yml",
]

DOC_PATTERNS = ["README*", "CONTRIBUTING*", "ARCHITECTURE*", "DEVELOPMENT*", "SECURITY*",
                "CHANGELOG*", "CODEOWNERS", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE*"]
ADR_DIRS = ["docs/adr", "docs/adrs", "doc/adr", "adr", "docs/decisions", "architecture/decisions"]

TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.py$|.*\.(test|spec)\.[cm]?[jt]sx?$|.*_test\.go$|.*(Test|Tests|IT)\.(java|kt)$|.*_spec\.rb$|.*Test\.php$)"
)
INTERESTING_DEPS = {
    "test": ["jest", "vitest", "mocha", "jasmine", "ava", "@playwright/test", "cypress",
             "pytest", "hypothesis", "unittest2", "nose2", "@testing-library/react"],
    "lint_format": ["eslint", "prettier", "@biomejs/biome", "ruff", "black", "flake8",
                    "pylint", "mypy", "pyright", "isort", "stylelint", "oxlint", "typescript"],
    "framework": ["react", "next", "vue", "nuxt", "svelte", "@sveltejs/kit", "angular",
                  "@angular/core", "solid-js", "astro", "remix", "@remix-run/react", "express",
                  "fastify", "@nestjs/core", "hono", "django", "flask", "fastapi", "starlette",
                  "langgraph", "langchain", "celery", "sqlalchemy", "prisma", "drizzle-orm",
                  "spring-boot-starter-web", "spring-boot-starter-webflux", "spring-boot-starter-data-jpa",
                  "spring-boot-starter-security", "quarkus-core", "micronaut-core", "hibernate-core",
                  "flyway-core", "liquibase-core", "lombok", "mapstruct"],
    "jvm_test": ["junit-jupiter", "junit", "spring-boot-starter-test", "mockito-core", "assertj-core",
                 "testcontainers", "rest-assured", "h2"],
    "datastore": ["postgresql", "mysql-connector-j", "mssql-jdbc", "ojdbc8", "ojdbc11", "sqlite-jdbc",
                  "mongodb-driver-sync", "jedis", "psycopg", "psycopg2", "psycopg2-binary", "asyncpg",
                  "pg", "mysql2", "mongoose", "redis", "ioredis"],
    "ui": ["tailwindcss", "@mui/material", "@chakra-ui/react", "antd", "bootstrap",
           "styled-components", "@emotion/react", "@radix-ui/react-dialog", "shadcn",
           "@headlessui/react", "vuetify", "primevue", "sass"],
}


def read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def walk(root: Path, max_depth: int):
    """Yield files under root, skipping ignored dirs, up to max_depth levels."""
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in IGNORED_DIRS or (entry.name.startswith(".") and entry.name not in {".github", ".cursor", ".claude", ".devcontainer", ".circleci", ".buildkite", ".husky"}):
                    continue
                if depth < max_depth:
                    stack.append((entry, depth + 1))
            else:
                yield entry


def load_toml(path: Path) -> dict:
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(read_text(path))
    except Exception:
        return {}


def match_deps(names) -> dict:
    names = {n.lower() for n in names}
    return {cat: sorted(d for d in deps if d in names) for cat, deps in INTERESTING_DEPS.items()
            if any(d in names for d in deps)}


def py_dep_names(specs) -> list:
    return [re.split(r"[\s<>=!~\[;@]", s.strip(), maxsplit=1)[0] for s in specs if s.strip()]


def describe_manifest(root: Path, path: Path) -> dict:
    info = {"path": rel(root, path), "stack": MANIFESTS[path.name]}
    name = path.name
    if name == "package.json":
        try:
            pkg = json.loads(read_text(path))
        except json.JSONDecodeError as exc:
            info["error"] = f"invalid JSON: {exc}"
            return info
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        info.update({
            "name": pkg.get("name"),
            "scripts": pkg.get("scripts", {}),
            "packageManager": pkg.get("packageManager"),
            "engines": pkg.get("engines"),
            "workspaces": pkg.get("workspaces"),
            "type": pkg.get("type"),
            "embedded_configs": [k for k in ["eslintConfig", "prettier", "jest", "babel", "browserslist",
                                             "stylelint", "lint-staged", "husky", "commitlint"] if k in pkg],
            "notable_deps": match_deps(deps),
        })
    elif name == "pyproject.toml":
        data = load_toml(path)
        project = data.get("project", {})
        poetry = data.get("tool", {}).get("poetry", {})
        deps = py_dep_names(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            deps += py_dep_names(group)
        for group in data.get("dependency-groups", {}).values():
            deps += py_dep_names(g for g in group if isinstance(g, str))
        deps += list(poetry.get("dependencies", {}))
        for group in poetry.get("group", {}).values():
            deps += list(group.get("dependencies", {}))
        info.update({
            "name": project.get("name") or poetry.get("name"),
            "requires_python": project.get("requires-python"),
            "scripts": project.get("scripts") or poetry.get("scripts"),
            "build_backend": data.get("build-system", {}).get("build-backend"),
            "tool_sections": sorted(data.get("tool", {})),
            "notable_deps": match_deps(deps),
        })
        if tomllib is None:
            info["warning"] = "Python < 3.11: pyproject.toml not parsed"
    elif name == "requirements.txt":
        lines = [l for l in read_text(path).splitlines() if l.strip() and not l.startswith(("#", "-"))]
        info["notable_deps"] = match_deps(py_dep_names(lines))
    elif name == "Cargo.toml":
        data = load_toml(path)
        info["workspace_members"] = data.get("workspace", {}).get("members")
        info["name"] = data.get("package", {}).get("name")
    elif name == "go.mod":
        m = re.search(r"^module\s+(\S+)", read_text(path), re.M)
        g = re.search(r"^go\s+(\S+)", read_text(path), re.M)
        info["module"] = m.group(1) if m else None
        info["go_version"] = g.group(1) if g else None
    elif name == "pom.xml":
        info.update(describe_pom(path))
        info["wrapper"] = "./mvnw" if (path.parent / "mvnw").exists() else None
    elif name in {"build.gradle", "build.gradle.kts"}:
        text = read_text(path)
        info["wrapper"] = "./gradlew" if (path.parent / "gradlew").exists() else None
        jv = re.search(r"(?:JavaLanguageVersion\.of\(|sourceCompatibility\s*=\s*['\"]?(?:JavaVersion\.VERSION_)?)(\d+)", text)
        info["java_version"] = jv.group(1) if jv else None
        info["plugins"] = sorted(set(re.findall(r"id\s*\(?\s*['\"]([\w.-]+)['\"]", text)))[:30]
        info["notable_deps"] = match_deps(re.findall(r"['\"][\w.-]+:([\w.-]+)(?::[^'\"]*)?['\"]", text))
    elif name == "composer.json":
        try:
            info["scripts"] = json.loads(read_text(path)).get("scripts", {})
        except json.JSONDecodeError:
            pass
    return info


def describe_pom(path: Path) -> dict:
    import xml.etree.ElementTree as ET
    try:
        tree = ET.fromstring(read_text(path))
    except ET.ParseError as exc:
        return {"error": f"invalid pom.xml: {exc}"}
    ns = {"m": tree.tag[1:].split("}")[0]} if tree.tag.startswith("{") else {}

    def q(xpath):
        return "/".join(f"m:{x}" for x in xpath.split("/")) if ns else xpath

    def text_of(xpath):
        el = tree.find(q(xpath), ns)
        return el.text.strip() if el is not None and el.text else None

    props = {}
    pnode = tree.find(q("properties"), ns)
    if pnode is not None:
        for child in pnode:
            props[child.tag.split("}")[-1]] = (child.text or "").strip()
    java = next((props[k] for k in ["java.version", "maven.compiler.release", "maven.compiler.source",
                                    "maven.compiler.target"] if props.get(k)), None)
    deps = [d.text for d in tree.iterfind(".//" + q("dependency/artifactId"), ns) if d.text]
    plugins = [p.text for p in tree.iterfind(".//" + q("plugin/artifactId"), ns) if p.text]
    return {
        "name": text_of("artifactId"),
        "parent": "/".join(filter(None, [text_of("parent/artifactId"), text_of("parent/version")])) or None,
        "java_version": java,
        "packaging": text_of("packaging") or "jar",
        "modules": [m.text for m in tree.iterfind(q("modules/module"), ns)] or None,
        "profiles": [p.text for p in tree.iterfind(q("profiles/profile/id"), ns)] or None,
        "plugins": sorted(set(plugins)),
        "notable_deps": match_deps(deps),
    }


def compose_services(path: Path) -> dict:
    """Light scan of a compose file (no PyYAML): service -> image/build, ports, depends_on, env_file."""
    services, current, section, in_services = {}, None, None, False
    for line in read_text(path).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            in_services = stripped.startswith("services:")
            current = None
            continue
        if not in_services:
            continue
        if indent == 2 and stripped.endswith(":"):
            current, section = stripped[:-1], None
            services[current] = {}
        elif current and indent == 4:
            key, _, value = stripped.partition(":")
            section, value = key, value.strip()
            if key in {"image", "build", "container_name", "env_file"} and value:
                services[current][key] = value.strip("'\"")
            elif key in {"ports", "depends_on", "profiles"} and value.startswith("["):
                services[current][key] = [v.strip(" '\"") for v in value.strip("[]").split(",") if v.strip()]
        elif current and indent >= 6 and stripped.startswith("- ") and section in {"ports", "depends_on", "profiles", "env_file"}:
            services[current].setdefault(section, []).append(stripped[2:].strip("'\""))
    return services


def dockerfile_facts(path: Path) -> dict:
    text = read_text(path)
    return {"from": re.findall(r"^FROM\s+(\S+)", text, re.M | re.I),
            "expose": re.findall(r"^EXPOSE\s+(.+)$", text, re.M | re.I)}


NET_RE = re.compile(r"\b(curl|wget|psql|mysql|sqlcmd|mongosh|ssh|scp|rsync|kubectl|aws|gcloud|terraform"
                    r"|docker\s+push|npm\s+publish|https?://(?!localhost|127\.0\.0\.1)[\w.-]+)")


def risk_signals(root: Path, files: list) -> dict:
    """Things an agent must not run blindly: raw SQL, migrations, scripts that reach networks or DBs."""
    sql_dirs = {}
    for f in files:
        if f.suffix.lower() == ".sql":
            d = rel(root, f.parent) or "."
            sql_dirs[d] = sql_dirs.get(d, 0) + 1
    migration_dirs = sorted({rel(root, f.parent) for f in files if re.search(
        r"(^|/)(migrations?|db/migrate|alembic/versions|flyway|liquibase|changelog)(/|$)", rel(root, f.parent))})
    scripts = {}
    for f in files:
        r = rel(root, f)
        if f.suffix in {".sh", ".ps1", ".bat", ".cmd", ".mjs", ".js", ".py"} and re.search(r"(^|/)(scripts?|bin|tools|deploy)/", r):
            hits = sorted({m.group(1) for m in NET_RE.finditer(read_text(f, 50_000))})
            if hits:
                scripts[r] = hits[:8]
    return {"sql_files_by_dir": sql_dirs, "migration_dirs": migration_dirs[:20],
            "scripts_touching_network_or_db": scripts}


def suggested_commands(manifests: list, lockfiles: list, task_runners: dict) -> list:
    """Candidate commands per stack. UNVERIFIED: the agent must run each one."""
    out = []
    pms = {m for _, m in lockfiles}
    for m in manifests:
        parent = Path(m["path"]).parent.as_posix()
        where = "." if parent in {"", "."} else parent
        st = m["stack"]

        def add(task, cmd):
            out.append({"dir": where, "task": task, "cmd": cmd})

        if st == "node":
            pm = next((p for p in ["pnpm", "yarn", "bun", "npm"] if p in pms), None)
            add("install", {"npm": "npm ci", "pnpm": "pnpm install --frozen-lockfile",
                            "yarn": "yarn install --frozen-lockfile", "bun": "bun install --frozen-lockfile",
                            None: "npm install"}[pm])
            for task in ["build", "lint", "typecheck", "type-check", "test", "format:check", "check"]:
                if task in (m.get("scripts") or {}):
                    add(task, f"{pm or 'npm'} run {task}")
        elif st == "python":
            if "uv" in pms:
                add("install", "uv sync --frozen"); add("test", "uv run pytest -q")
            elif "poetry" in pms:
                add("install", "poetry install"); add("test", "poetry run pytest -q")
            elif m["path"].endswith("pyproject.toml"):
                add("install", "uv venv -p <supported version> && uv pip install -e '.[<test extras>]'")
                add("test", "<venv python> -m pytest -q")
            lint = m.get("notable_deps", {}).get("lint_format") or []
            if "ruff" in (m.get("tool_sections") or []) or "ruff" in lint:
                add("lint", "ruff check . && ruff format --check .")
        elif st == "java-maven":
            mvn = m.get("wrapper") or "mvn"
            add("build+test", f"{mvn} -B verify")
            add("package, no tests", f"{mvn} -B -DskipTests package")
            add("single test", f"{mvn} -B test -Dtest=ClassName#method")
        elif st == "jvm-gradle":
            g = m.get("wrapper") or "gradle"
            add("build+test", f"{g} build"); add("single test", f"{g} test --tests 'ClassName.method'")
        elif st == "go":
            add("build", "go build ./..."); add("test", "go test ./..."); add("lint", "go vet ./...")
        elif st == "rust":
            add("build", "cargo build"); add("test", "cargo test")
            add("lint", "cargo clippy -- -D warnings && cargo fmt --check")
    for runner, targets in task_runners.items():
        tool = "make" if runner.endswith("Makefile") else ("just" if runner.lower().endswith("justfile") else "task")
        parent = Path(runner).parent.as_posix()
        for t in targets:
            if t in {"test", "lint", "build", "check", "fmt", "format", "typecheck", "ci", "setup", "install"}:
                out.append({"dir": "." if parent in {"", "."} else parent, "task": t, "cmd": f"{tool} {t}"})
    return out


def sql_facts(root: Path, files: list) -> list:
    """Per SQL file: size, encoding, dialect hints. Helps tell real schema scripts from legacy dumps."""
    out = []
    for f in files:
        if f.suffix.lower() != ".sql":
            continue
        raw = f.read_bytes()[:20_000]
        enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-bom" if raw[:3] == b"\xef\xbb\xbf" else "utf-8/ascii")
        text = raw.decode("utf-16" if enc == "utf-16" else "utf-8", errors="replace")
        hints = []
        if re.search(r"^\s*GO\s*$|USE \[|\bNVARCHAR\b|\bIDENTITY\(", text, re.M | re.I):
            hints.append("sqlserver")
        if re.search(r"\bSERIAL\b|CREATE EXTENSION|\bJSONB\b|::\w+|\$\$", text, re.I):
            hints.append("postgres")
        if re.search(r"ENGINE=InnoDB|AUTO_INCREMENT", text, re.I):
            hints.append("mysql")
        if re.search(r"\bDROP\s+(TABLE|SCHEMA|DATABASE)\b", text, re.I):
            hints.append("DROPS objects")
        out.append({"path": rel(root, f), "kb": round(f.stat().st_size / 1024), "encoding": enc, "hints": hints})
    return sorted(out, key=lambda x: x["path"])[:40]


def schema_management(manifests: list, files: list, root: Path) -> list:
    tools = set()
    for m in manifests:
        deps = {d for cat in (m.get("notable_deps") or {}).values() for d in cat}
        tools |= deps & {"flyway-core", "liquibase-core", "prisma", "drizzle-orm", "sqlalchemy"}
    names = {f.name for f in files}
    if "alembic.ini" in names:
        tools.add("alembic")
    if any(re.search(r"/migrations/\d{4}_", rel(root, f)) for f in files if f.suffix == ".py"):
        tools.add("django-migrations")
    if any(re.search(r"db/migrate/\d+_", rel(root, f)) for f in files):
        tools.add("rails-migrations")
    return sorted(tools) or ["none detected (schema likely managed by raw SQL scripts or externally)"]


def external_hosts_in_config(root: Path, files: list) -> list:
    """Non-local hosts that config defaults point to (host names only; never values of secrets)."""
    out = []
    for f in files:
        if not (re.match(r"^application(-[\w]+)?\.(properties|ya?ml)$", f.name) or f.name.startswith(".env.")
                and re.search(r"(example|sample|template|dist)$", f.name) or re.match(r"^(docker-)?compose", f.name)):
            continue
        for line in read_text(f).splitlines():
            if line.lstrip().startswith("#"):
                continue
            for host in re.findall(r"(?:://|[:=]\s*|:-)((?:[a-z0-9-]+\.)+(?:com|io|net|org|dev|app|cloud|mx|co|us|eu)\b)", line, re.I):
                key = re.split(r"[=:]", line.strip(), maxsplit=1)[0].strip()[:60]
                if host not in {"example.com", "example.org"} and key not in {"image", "- image"}:
                    out.append({"file": rel(root, f), "key": key, "host": host})
    return out[:40]


def container_conflicts(compose: dict) -> list:
    """Compose container names / host ports already used by containers running on THIS machine."""
    docker = shutil.which("docker")
    if not docker or not compose:
        return []
    try:
        res = subprocess.run([docker, "ps", "--format", "{{.Names}}\t{{.Ports}}"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return [{"warning": "docker daemon not reachable"}]
    running = [l.split("\t") + [""] for l in res.stdout.splitlines() if l.strip()]
    used_ports = {m for _, ports, *_ in running for m in re.findall(r":(\d+)->", ports)}
    names = {n for n, *_ in running}
    out = []
    for file, services in compose.items():
        for svc, info in services.items():
            if info.get("container_name") in names:
                out.append({"compose": file, "service": svc, "conflict": f"container name '{info['container_name']}' already running"})
            for port in info.get("ports", []):
                host = re.match(r"^(?:[\d.]+:)?(?:\$\{\w+:-)?(\d+)\}?:", str(port))
                if host and host.group(1) in used_ports:
                    out.append({"compose": file, "service": svc, "conflict": f"host port {host.group(1)} already in use"})
    return out


def make_targets(path: Path) -> list:
    text = read_text(path)
    if path.name == "Makefile":
        return sorted(set(re.findall(r"^([A-Za-z0-9][\w.-]*)\s*:(?!=)", text, re.M)) - {".PHONY"})
    if path.name.lower() == "justfile":
        return sorted(set(re.findall(r"^@?([A-Za-z0-9][\w-]*)(?:\s+[^:=\n]*)?:(?!=)", text, re.M)))
    return sorted(set(re.findall(r"^  ([A-Za-z0-9][\w:-]*):\s*$", text, re.M)))  # Taskfile


def ci_commands(path: Path) -> list:
    """Extract shell commands from CI config (single-line and block `run:`/`script:` entries)."""
    cmds, lines = [], read_text(path).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)-?\s*(run|script|command):\s*(.*)$", line)
        if m:
            indent, value = len(m.group(1)), m.group(3).strip()
            if value in {"|", ">", "|-", ">-"}:
                i += 1
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                    if lines[i].strip():
                        cmds.append(lines[i].strip())
                    i += 1
                continue
            if value and not value.startswith(("[", "{")):
                cmds.append(value.strip("'\""))
        elif re.match(r"^\s*-\s+(?!name:|uses:|with:)[a-z]", line) and path.name == ".gitlab-ci.yml":
            cmds.append(line.strip()[2:])
        i += 1
    joined = []
    for c in cmds:  # re-join shell line continuations ("cmd \" + next line)
        if joined and joined[-1].endswith("\\"):
            joined[-1] = joined[-1][:-1].rstrip() + " " + c
        else:
            joined.append(c)
    seen, out = set(), []
    for c in joined:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:80]


ENV_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", re.M)
ENV_IN_CODE_RE = re.compile(
    r"(?:os\.environ(?:\.get)?\s*[\[(]\s*|os\.getenv\(\s*|getenv\(\s*|process\.env\.|process\.env\[\s*"
    r"|import\.meta\.env\.|env::var\(\s*|os\.Getenv\(\s*|System\.getenv\(\s*|ENV\[\s*|\$_ENV\[\s*)"
    r"['\"]?([A-Z][A-Z0-9_]{2,})"
)
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt",
                 ".rb", ".php", ".cs", ".sh"}


def git_tracked(root: Path, names: list) -> list:
    """Return which of `names` are tracked by git (empty if git is unavailable)."""
    if not (root / ".git").exists():
        return []
    try:
        res = subprocess.run(["git", "-C", str(root), "ls-files", "--", *names],
                             capture_output=True, text=True, timeout=10)
        return res.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []


def env_facts(root: Path, files: list) -> dict:
    """Export env NAMES only; read templates/code, not values from real env files."""
    out = {}
    for name in [".env.example", ".env.sample", ".env.template", ".env.dist", "example.env", "env.example"]:
        p = root / name
        if p.exists():
            out[name] = ENV_KEY_RE.findall(read_text(p))
    present = [n for n in [".env", ".env.local", ".env.development", ".env.production", ".env.test"] if (root / n).exists()]
    if present:
        tracked = set(git_tracked(root, present))
        out["env_files"] = [{"path": n, "tracked_by_git": n in tracked} for n in present]
    used = {}
    for f in files:
        if f.suffix in {".properties", ".yml", ".yaml", ".toml", ".conf"} and ".github" not in f.parts:
            for key in set(re.findall(r"\$\{([A-Z][A-Z0-9_]{2,})(?::[^}]*)?\}", read_text(f, 100_000))):
                used.setdefault(key, []).append(rel(root, f))
        if f.suffix in CODE_SUFFIXES:
            for key in set(ENV_IN_CODE_RE.findall(read_text(f, 100_000))):
                used.setdefault(key, []).append(rel(root, f))
    if used:
        out["read_in_code_or_config"] = {k: sorted(v)[:5] for k, v in sorted(used.items())}
    return out


def toolchain() -> dict:
    """Which runtimes / package managers are installed on THIS machine, with versions."""
    candidates = ["node", "npm", "pnpm", "yarn", "bun", "deno", "python", "python3", "py", "uv",
                  "poetry", "pip", "go", "cargo", "java", "mvn", "gradle", "php", "composer",
                  "ruby", "bundle", "dotnet", "docker", "make", "just"]
    out = {}
    for tool in candidates:
        path = shutil.which(tool)
        if not path:
            continue
        try:
            arg = "version" if tool == "go" else "--version"
            res = subprocess.run([path, arg], capture_output=True, text=True, timeout=8)
            line = (res.stdout or res.stderr).strip().splitlines()
            if res.returncode != 0:
                # e.g. Windows Store "python" aliases: on PATH but not a real interpreter.
                out[tool] = f"on PATH but broken: {line[0][:60] if line else 'exit ' + str(res.returncode)}"
            else:
                out[tool] = line[0][:80] if line else "installed"
        except (OSError, subprocess.SubprocessError):
            out[tool] = "on PATH but version check failed"
    return out


WATCH_MODE_RE = re.compile(r"(react-scripts test|vue-cli-service test:unit|ng test|karma start"
                           r"|jest\b.*--watch|vitest(?!\s+run)(\s|$)|nodemon|--watch\b)")


def script_warnings(manifests: list) -> list:
    """Flag manifest scripts that block (watch mode) when run non-interactively."""
    warnings = []
    for m in manifests:
        for name, cmd in (m.get("scripts") or {}).items():
            if isinstance(cmd, str) and WATCH_MODE_RE.search(cmd) and not name.startswith(("dev", "start", "serve", "watch")):
                warnings.append({"manifest": m["path"], "script": name, "command": cmd,
                                 "warning": "may start interactive/watch mode and never exit"})
    return warnings


def tree_summary(root: Path) -> list:
    out = []
    for entry in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name)):
        if entry.name in IGNORED_DIRS:
            continue
        if entry.is_dir():
            children = [c.name for c in sorted(entry.iterdir()) if c.name not in IGNORED_DIRS]
            item = {"dir": entry.name, "children": children[:15]}
            if len(children) > 15:
                item["more_not_listed"] = len(children) - 15
            out.append(item)
        else:
            out.append({"file": entry.name})
    return out


def audit_agent_docs(root: Path, docs: list) -> list:
    """Flag backticked paths in existing agent docs that no longer exist."""
    findings = []
    path_re = re.compile(r"`([\w./-]+/[\w./-]*|[\w-]+\.(?:md|py|ts|tsx|js|json|toml|ya?ml|go|rs|sh|cfg|ini))`")
    for doc in docs:
        p = root / doc["path"]
        if p.is_dir():
            continue
        base = p.parent
        missing = []
        for ref in sorted(set(path_re.findall(read_text(p)))):
            if ref.startswith(("http", "~", "/")) or "*" in ref:
                continue
            if not (root / ref).exists() and not (base / ref).exists():
                missing.append(ref)
        findings.append({"doc": doc["path"], "missing_paths": missing})
    return findings


BRAIN_DIR = "docs/agents"
DOMAIN_CONTAINERS = {"src", "app", "apps", "lib", "libs", "packages", "services", "modules", "internal", "pkg", "cmd"}
NON_DOMAIN_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "fixtures", "docs", "doc",
                   "examples", "assets", "migrations"}
SOURCE_EXTS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".go", ".rs",
               ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".cs", ".fs", ".swift", ".c", ".h",
               ".cpp", ".hpp", ".ex", ".exs", ".erl", ".clj", ".dart", ".lua"}


def brain_candidates(root: Path, files: list) -> dict:
    """Candidate domains for a docs/agents brain: where source code branches into areas."""
    total, direct = {}, {}
    for f in files:
        parts = f.relative_to(root).parts[:-1]
        if (f.suffix.lower() not in SOURCE_EXTS or TEST_FILE_RE.match(f.name) or not parts
                or {p.lower() for p in parts} & NON_DOMAIN_DIRS):
            continue
        direct["/".join(parts)] = direct.get("/".join(parts), 0) + 1
        for i in range(1, len(parts) + 1):
            total["/".join(parts[:i])] = total.get("/".join(parts[:i]), 0) + 1

    def children(d):
        return sorted(c for c in total if c.startswith(d + "/") and c.count("/") == d.count("/") + 1)

    domains = []
    for top in (d for d in total if "/" not in d):
        if top.lower() not in DOMAIN_CONTAINERS:
            domains.append(top)
            continue
        d = top
        while not direct.get(d) and len(children(d)) == 1:  # collapse src/main/java/com/acme chains
            d = children(d)[0]
        domains.extend(children(d) if len(children(d)) >= 2 else [d])
    brain = root / BRAIN_DIR
    return {
        "brain_dir": BRAIN_DIR,
        "brain_dir_exists": brain.is_dir(),
        "existing_brain_files": sorted(rel(root, f) for f in brain.rglob("*.md")) if brain.is_dir() else [],
        "domains": sorted(({"path": d, "source_files": total[d]} for d in domains),
                          key=lambda x: (-x["source_files"], x["path"]))[:25],
    }


def collect(root: Path, max_depth: int, audit: bool, brain: bool = False) -> dict:
    files = list(walk(root, max_depth))
    by_name = {}
    for f in files:
        by_name.setdefault(f.name, []).append(f)

    manifests = [describe_manifest(root, f) for name in MANIFESTS for f in by_name.get(name, [])]
    manifests.sort(key=lambda m: (m["path"].count("/"), m["path"]))

    lockfiles = sorted({(rel(root, f), LOCKFILES[f.name]) for n in LOCKFILES for f in by_name.get(n, [])})

    configs = sorted(c for c in TOOL_CONFIGS if (root / c).exists())
    nested_configs = sorted({rel(root, f) for c in TOOL_CONFIGS for f in by_name.get(Path(c).name, [])
                             if f.parent != root} - set(configs))

    task_runners = {}
    for name in ["Makefile", "justfile", "Justfile", "Taskfile.yml", "Taskfile.yaml"]:
        for f in by_name.get(name, []):
            task_runners[rel(root, f)] = make_targets(f)

    ci = {}
    for pattern in CI_GLOBS:
        for f in sorted(root.glob(pattern)):
            ci[rel(root, f)] = ci_commands(f)

    agent_docs = []
    for d in AGENT_DOCS:
        for f in [root / d] + [x for x in by_name.get(Path(d).name, []) if x.parent != root and "/" not in d]:
            if f.exists() and f.is_file():
                text = read_text(f)
                agent_docs.append({
                    "path": rel(root, f),
                    "lines": text.count("\n") + 1,
                    "has_agentify_markers": "<!-- agentify:start -->" in text,
                    "imports": re.findall(r"^@(\S+)", text, re.M),
                })
    for d in AGENT_DOC_DIRS:
        if (root / d).is_dir():
            agent_docs.append({"path": d, "dir_entries": sorted(p.name for p in (root / d).iterdir())[:30]})
    seen, unique_docs = set(), []
    for d in agent_docs:
        if d["path"] not in seen:
            seen.add(d["path"])
            unique_docs.append(d)

    docs = sorted({rel(root, f) for pat in DOC_PATTERNS for f in root.glob(pat) if f.is_file()})
    adrs = {d: len(list((root / d).glob("*.md"))) for d in ADR_DIRS if (root / d).is_dir()}
    if (root / "docs").is_dir():
        docs.append(f"docs/ ({sum(1 for _ in (root / 'docs').rglob('*.md'))} .md files)")

    test_files = [f for f in files if TEST_FILE_RE.match(f.name)]
    test_dirs = {}
    for f in test_files:
        top = rel(root, f).split("/")[0] if "/" in rel(root, f) else "."
        test_dirs[top] = test_dirs.get(top, 0) + 1

    compose = {rel(root, f): compose_services(f) for f in files
               if re.match(r"^(docker-)?compose([.-][\w.-]+)?\.ya?ml$", f.name)}
    dockerfiles = {rel(root, f): dockerfile_facts(f) for f in files
                   if f.name == "Dockerfile" or f.name.startswith("Dockerfile.") or f.name.endswith(".Dockerfile")}
    root_markdown = sorted(f.name for f in root.glob("*.md") if f.name not in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"})
    nested_readmes = sorted(rel(root, f) for f in files if f.name.lower().startswith("readme") and f.parent != root)
    app_configs = sorted({rel(root, f) for f in files
                          if re.match(r"^application(-[\w]+)?\.(properties|ya?ml)$", f.name)
                          or re.match(r"^appsettings(\.\w+)?\.json$", f.name)
                          or f.name in {"settings.py", "config.exs", "next.config.js", "vite.config.ts", "vite.config.js"}})

    stacks = sorted({m["stack"] for m in manifests})
    monorepo_signals = [c for c in ["pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "go.work", "rush.json"] if c in configs]
    if any(m.get("workspaces") or m.get("workspace_members") for m in manifests):
        monorepo_signals.append("workspaces in manifest")
    if sum(1 for m in manifests if m["path"].count("/") > 0) >= 2:
        monorepo_signals.append(f"{sum(1 for m in manifests if '/' in m['path'])} nested manifests")

    tracked = set(MANIFESTS) | set(LOCKFILES) | {Path(c).name for c in TOOL_CONFIGS}
    empty_or_stub = sorted(
        rel(root, f) for f in files
        if f.name in tracked and f.stat().st_size < 64 and read_text(f).strip() in {"", "{}", "[]"}
    ) + sorted(rel(root, f) for f in test_files if f.stat().st_size == 0)

    result = {
        "root": str(root.resolve()),
        "empty_or_stub_files": empty_or_stub,
        "is_git_repo": (root / ".git").exists(),
        "stacks": stacks,
        "monorepo_signals": monorepo_signals,
        "manifests": manifests,
        "lockfiles": [{"path": p, "manager": m} for p, m in lockfiles],
        "tool_configs_root": configs,
        "tool_configs_nested": nested_configs[:60],
        "task_runners": task_runners,
        "ci": ci,
        "agent_docs": unique_docs,
        "docs": sorted(set(docs) | set(root_markdown) | set(nested_readmes[:30])),
        "app_configs": app_configs[:30],
        "containers": {"compose": compose, "dockerfiles": dockerfiles,
                       "conflicts_on_this_machine": container_conflicts(compose)},
        "schema_management": schema_management(manifests, files, root),
        "sql_files": sql_facts(root, files),
        "external_hosts_in_config": external_hosts_in_config(root, files),
        "risk_signals": risk_signals(root, files),
        "suggested_commands_UNVERIFIED": suggested_commands(manifests, lockfiles, task_runners),
        "adr_dirs": adrs,
        "env_vars": env_facts(root, files),
        "script_warnings": script_warnings(manifests),
        "toolchain_on_this_machine": toolchain(),
        "tests": {"file_count": len(test_files), "by_top_dir": test_dirs},
        "tree": tree_summary(root),
        "scan": {"max_depth": max_depth, "files_scanned": len(files)},
    }
    if audit:
        result["audit"] = audit_agent_docs(root, [d for d in unique_docs if "lines" in d])
    if brain:
        result["brain_candidates"] = brain_candidates(root, files)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("--audit", action="store_true", help="check paths referenced by existing agent docs")
    parser.add_argument("--brain", action="store_true", help="add candidate domains for a docs/agents brain")
    parser.add_argument("--max-depth", type=int, default=12,
                        help="directory depth to scan (default: 12; Java packages nest deeply)")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    json.dump(collect(root, args.max_depth, args.audit, args.brain), sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
