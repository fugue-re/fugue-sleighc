import asyncio
import pathlib
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from .log import DIM, GREEN, RED, RESET, status

SYSTEM_PROMPT = """\
You are reconciling vendored/CMakeLists.txt against a freshly imported set
of Ghidra C++ sources in vendored/src/.

Goal: make this command succeed:
    cmake -S vendored -B target/ghidra-update-build \\
        -DBUILD_COMPILER=ON -DBUILD_DECOMPILER=ON
    cmake --build target/ghidra-update-build -j

Rules:
  - Only edit vendored/CMakeLists.txt. Never touch any file in vendored/src/
    (those are upstream Ghidra sources -- modifying them creates maintenance
    debt for every future release).
  - Preserve the two-target structure. SLEIGH_SOURCES feeds the sleighc
    executable; DECOMPILER_SOURCES feeds the decompiler static lib. Both
    target lists must remain present even though the outer Rust crate only
    builds the compiler.
  - Default new .cc files to DECOMPILER_SOURCES only. Add to SLEIGH_SOURCES
    only when a build error proves it is required by the compiler target.
  - For new .y or .l files, add BISON_TARGET / FLEX_TARGET entries
    matching the existing pattern (output to ${{CMAKE_CURRENT_BINARY_DIR}}/generated)
    and wire them into the appropriate add_executable / add_library call.
  - For files that disappeared upstream, remove their entries.
  - Do not commit, push, or run git operations beyond `git status` / `git diff`.
  - Stop as soon as the build is green. Do not refactor or reformat.

Iteration budget: 10 build attempts. If still red, summarize what is
blocking and stop.

Files are relative to the repository root: {repo_root}
"""

INITIAL_PROMPT_TEMPLATE = """\
The importer has just imported a new Ghidra release into vendored/src/ and
produced this report:

```
{report}
```

Please:
  1. Read vendored/CMakeLists.txt.
  2. Reconcile its source lists against vendored/src/ per the rules.
  3. Run the configure + build commands from the system prompt to verify.
  4. Iterate on errors until the build is green, then stop.

Files are relative to the repository root: {repo_root}
"""


def _tool_summary(name: str, inp: dict, repo_root: pathlib.Path) -> str:
    if name in ("Read", "Edit", "Write"):
        path = inp.get("file_path", "")
        try:
            path = str(pathlib.Path(path).relative_to(repo_root))
        except ValueError:
            pass
        if name == "Edit":
            old = inp.get("old_string", "").splitlines()
            new = inp.get("new_string", "").splitlines()
            return f"{path} (-{len(old)}/+{len(new)} lines)"
        return path
    if name == "Bash":
        cmd = inp.get("command", "").strip().splitlines()
        first = cmd[0] if cmd else ""
        suffix = f" ... (+{len(cmd) - 1} lines)" if len(cmd) > 1 else ""
        return (first[:140] + ("…" if len(first) > 140 else "")) + suffix
    if name in ("Glob", "Grep"):
        return inp.get("pattern", "")
    return str(inp)[:140]


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _log_message(message, repo_root: pathlib.Path) -> None:
    if isinstance(message, SystemMessage):
        if message.subtype == "init":
            data = message.data or {}
            model = data.get("model", "?")
            tools = data.get("tools") or []
            status(f"agent ready (model={model}, tools={len(tools)})")
        return

    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text.rstrip()
                if text:
                    print(text, flush=True)
            elif isinstance(block, ThinkingBlock):
                first = block.thinking.strip().splitlines()
                if first:
                    print(
                        f"{DIM}thinking: {first[0][:140]}{RESET}",
                        file=sys.stderr,
                        flush=True,
                    )
            elif isinstance(block, ToolUseBlock):
                status(f"{block.name}: {_tool_summary(
                    block.name, block.input, repo_root)}")
        return

    if isinstance(message, UserMessage):
        for block in message.content:
            if isinstance(block, ToolResultBlock) and block.is_error:
                tail = "\n".join(_result_text(
                    block.content).splitlines()[-12:])
                print(
                    f"{RED}   tool error:{RESET}\n{tail}",
                    file=sys.stderr,
                    flush=True,
                )
        return

    if isinstance(message, ResultMessage):
        color = GREEN if message.subtype == "success" else RED
        cost = f" cost=${
            message.total_cost_usd:.4f}" if message.total_cost_usd else ""
        turns = f" turns={message.num_turns}" if message.num_turns else ""
        duration = (
            f" duration={message.duration_ms /
                         1000:.1f}s" if message.duration_ms else ""
        )
        print(
            f"{color}==>{RESET} agent finished: {
                message.subtype}{turns}{duration}{cost}",
            file=sys.stderr,
            flush=True,
        )


async def _run(report_text: str, repo_root: pathlib.Path) -> str | None:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT.format(repo_root=repo_root),
        allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        model="claude-opus-4-7",
        cwd=str(repo_root),
        max_turns=10,
    )
    final: str | None = None
    async for message in query(
        prompt=INITIAL_PROMPT_TEMPLATE.format(
            report=report_text, repo_root=repo_root),
        options=options,
    ):
        _log_message(message, repo_root)
        if isinstance(message, ResultMessage):
            final = message.subtype
    return final


def reconcile(repo_root: pathlib.Path, report_text: str) -> int:
    status(f"working dir: {repo_root}")
    status(f"loaded report ({len(report_text)} bytes)")
    final = asyncio.run(_run(report_text, repo_root))
    if final != "success":
        print(f"\nagent ended with status: {final}", file=sys.stderr)
        return 1
    build_dir = repo_root / "target" / "ghidra-update-build"
    try:
        rel = build_dir.relative_to(repo_root)
    except ValueError:
        rel = build_dir
    status(f"build verified under {rel}")
    status("review `git -C vendored diff CMakeLists.txt` before committing")
    return 0
