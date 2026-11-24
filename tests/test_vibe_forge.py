from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

FORGE_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scaffold_guard = _load_module(
    "scaffold_guard",
    FORGE_ROOT / "skills" / "vibe-straightline-architect" / "scripts" / "scaffold_guard.py",
)
clean_slate_audit = _load_module(
    "clean_slate_audit",
    FORGE_ROOT / "skills" / "trail-clean-slate-debugger" / "scripts" / "clean_slate_audit.py",
)
live_verify_loop = _load_module(
    "live_verify_loop",
    FORGE_ROOT / "skills" / "vibe-closed-loop-verifier" / "scripts" / "live_verify_loop.py",
)
sync_integrations = _load_module(
    "sync_integrations",
    FORGE_ROOT / "scripts" / "sync_integrations.py",
)
installer = _load_module(
    "install",
    FORGE_ROOT / "install.py",
)


def test_plugin_manifest_and_skills_are_valid_and_lf_clean() -> None:
    manifest = json.loads((FORGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "cofi-vibe-forge"
    assert (FORGE_ROOT / manifest["logo"]).is_file()
    assert len(manifest["suggestedPrompts"]) == 3
    assert manifest["repository"] == "https://github.com/Cofi295/CofiVibeForge"

    mcp_example = json.loads((FORGE_ROOT / "mcp_config.example.json").read_text(encoding="utf-8"))
    assert "mcpServers" in mcp_example

    for skill_slug in ("trail", "vibe-straightline-architect", "trail-clean-slate-debugger", "vibe-closed-loop-verifier"):
        skill_md = FORGE_ROOT / "skills" / skill_slug / "SKILL.md"
        raw = skill_md.read_bytes()
        assert b"\r" not in raw, f"CRLF detected in {skill_md}"
        text = raw.decode("utf-8")
        assert text.startswith(f"---\nname: {skill_slug}\n")
        assert len(text) < 12000


def test_zero_personal_paths_in_git_tracked_files() -> None:
    res = subprocess.run(
        ["git", "-C", str(FORGE_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    assert "mcp_config.json" not in tracked_files
    assert "install.py" in tracked_files

    banned_tokens = (Path.home().name, "C:\\Users\\", "/Users/")
    for rel in tracked_files:
        content = (FORGE_ROOT / rel).read_text(encoding="utf-8")
        for token in banned_tokens:
            if rel == "tests/test_vibe_forge.py" and token in {"C:\\Users\\", "/Users/"}:
                continue
            assert token not in content, f"Leaked personal machine path token '{token}' in tracked file {rel}"


def test_forge_dogfoods_its_own_scaffold_guard() -> None:
    report = scaffold_guard.audit_target(FORGE_ROOT, max_lines=400)
    assert report["passed"], f"Self-audit failed: {report['issues']}"
    assert report["error_count"] == 0
    assert report["warning_count"] == 0


def test_scaffold_guard_catches_hallucinated_bloat_and_rogue_files(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text(
        "| File Path | Single Responsibility |\n"
        "| :--- | :--- |\n"
        "| `src/core.py` | Core logic |\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "core.py").write_text(
        "class SpeculativeProcessor:\n"
        "    def run(self, x: int) -> int:\n"
        "        return x + 1\n\n"
        "def compute(data: list[int], future_config: dict | None = None) -> int:\n"
        "    return sum(data)\n\n"
        "def compute_wrapper(items: list[int]) -> int:\n"
        "    return sum(items)\n",
        encoding="utf-8",
    )
    (src / "rogue_helper.py").write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")

    report = scaffold_guard.audit_target(tmp_path, blueprint=blueprint, max_lines=300)
    codes = {issue["code"] for issue in report["issues"]}
    assert not report["passed"]
    assert "SPECULATIVE_UNUSED_PARAM" in codes
    assert "SINGLE_METHOD_CLASS_BLOAT" in codes
    assert "TRIVIAL_PASSTHROUGH_WRAPPER" in codes
    assert "UNDECLARED_FILE" in codes


def test_scaffold_guard_passes_clean_straightline_module(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text(
        "| File Path | Single Responsibility |\n"
        "| :--- | :--- |\n"
        "| `src/pipeline.py` | Linear transform |\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "pipeline.py").write_text(
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\n"
        "class Summary:\n"
        "    total: int\n"
        "    count: int\n\n"
        "def summarize_scores(scores: list[int]) -> Summary:\n"
        "    valid = [s for s in scores if s >= 0]\n"
        "    return Summary(total=sum(valid), count=len(valid))\n",
        encoding="utf-8",
    )
    report = scaffold_guard.audit_target(tmp_path, blueprint=blueprint, max_lines=300)
    assert report["passed"]
    assert report["issues"] == []


def test_clean_slate_audit_blocks_band_aid_zombie_and_swallowed_errors() -> None:
    bad_diff = (
        "diff --git a/service.py b/service.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/service.py\n"
        "+++ b/service.py\n"
        "@@ -20,0 +21,14 @@\n"
        "+    # old_val = compute_wrong(x)\n"
        "+    # return old_val\n"
        "+    try:\n"
        "+        res = fallback_patch(x)\n"
        "+    except Exception: pass\n"
        "+    if res is None:\n"
        "+        res = 0\n"
        "+    if res < 0:\n"
        "+        res = 0\n"
        "+    if res > 100:\n"
        "+        res = 100\n"
        "+    return res\n"
    )
    issues = clean_slate_audit.audit_diff_text(bad_diff, mode="bugfix")
    codes = {i["code"] for i in issues}
    assert "BAND_AID_STACKING_SUSPECT" in codes
    assert "SWALLOWED_EXCEPTION" in codes
    assert "COMMENTED_ZOMBIE_CODE" in codes

    orphan_py = "import os\nimport math\n\ndef area(r: float) -> float:\n    return math.pi * r * r\n"
    src_issues = clean_slate_audit.audit_python_source("service.py", orphan_py)
    assert [i["code"] for i in src_issues] == ["ORPHAN_IMPORT"]

    drift_py = (
        "import subprocess\nimport sys\n\n"
        "def inspect_frames() -> dict:\n"
        "    return {'ok': True, 'static_hold_warning': True}\n\n"
        "def slice_clip() -> None:\n"
        "    p = subprocess.Popen(['echo', 'hi'])\n"
        "    fc = inspect_frames()\n"
        "    if fc.get('frozen'):\n"
        "        sys.stdout.write(str(p) + 'ensure_ascii=False')\n"
    )
    drift_issues = clean_slate_audit.audit_python_source("fetcher.py", drift_py)
    drift_codes = {i["code"] for i in drift_issues}
    assert "PRODUCER_CONSUMER_KEY_DRIFT" in drift_codes
    assert "UNCLOSED_SUBPROCESS_POPEN" in drift_codes
    assert "STDIO_UTF8_RECONFIGURE_MISSING" in drift_codes

    mock_test_py = (
        "def test_pipeline(monkeypatch):\n"
        "    monkeypatch.setattr('documentary.critic_loops.audit_footage_hygiene', lambda w, j: {'status': 'PASSED'})\n"
    )
    mock_issues = clean_slate_audit.audit_python_source("tests/test_edit.py", mock_test_py)
    assert {i["code"] for i in mock_issues} == {"MOCK_MASKED_CRITIC_GATE"}

    receipt = live_verify_loop.run_verification_suite(
        FORGE_ROOT,
        files=["install.py"],
        probes=[f'"{sys.executable}" -c "print(123)"'],
        check_cp1252=True,
        check_contradictions=True,
    )
    assert receipt["verdict"] == "VERIFIED_GREEN"
    assert receipt["passed"] is True
    assert len(receipt["receipt_id"]) == 16
    assert receipt["contradictions"]["enabled"] is True
    assert receipt["contradictions"]["passed"] is True
    assert len(receipt["probes"]) == 2


def test_producer_consumer_ast_no_false_positives_on_dynamic_or_local_dict_returns() -> None:
    # Early error literal + dynamic main return variable MUST NOT trigger false-positive drift
    dynamic_src = (
        "def _probe(path: str) -> dict:\n"
        "    return dict(ok=True, dhash='abc', corner_logo_detected=False)\n\n"
        "def inspect_frames(path: str) -> dict:\n"
        "    if not path:\n"
        "        return {'ok': False, 'reason': 'missing'}\n"
        "    info = _probe(path)\n"
        "    return info\n\n"
        "def audit(path: str) -> bool:\n"
        "    res = inspect_frames(path)\n"
        "    return bool(res.get('corner_logo_detected') or res.get('dhash'))\n"
    )
    assert clean_slate_audit.audit_python_source("critic.py", dynamic_src) == []

    # Static local dict built via AnnAssign + subscript catches genuine key typo without false positives
    local_static_src = (
        "def build_report(ok: bool) -> dict:\n"
        "    if not ok:\n"
        "        return {'ok': False, 'reason': 'bad'}\n"
        "    rep: dict = {'ok': True}\n"
        "    rep['score'] = 99\n"
        "    return rep\n\n"
        "def read_report() -> tuple:\n"
        "    r = build_report(True)\n"
        "    return (r.get('score'), r.get('nonexistent_key'))\n"
    )
    issues = clean_slate_audit.audit_python_source("report.py", local_static_src)
    assert [i["code"] for i in issues] == ["PRODUCER_CONSUMER_KEY_DRIFT"]
    assert "nonexistent_key" in issues[0]["message"]


def test_live_verify_loop_contradictions_forbid_and_signed_receipt(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "MIN_FOOTAGE_FLOOR = 0.50\n"
        "MIN_FOOTAGE_FLOOR = 0.0\n\n"
        "def compute(x: int) -> int:\n"
        "    return x + 1\n"
        "    dead = x + 2\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("MIN_FOOTAGE_FLOOR = 0.25\n", encoding="utf-8")

    receipt_md = tmp_path / "receipt.md"
    rc = live_verify_loop.main([
        "--repo", str(tmp_path),
        "--files", "a.py", "b.py",
        "--check-contradictions",
        "--forbid", r"MIN_FOOTAGE_FLOOR\s*=\s*0\.50",
        "--receipt-out", str(receipt_md),
    ])
    assert rc == 1
    md_text = receipt_md.read_text(encoding="utf-8")
    assert "FAILED_NEEDS_SELF_FIX" in md_text
    assert "DUPLICATE_SYMBOL_DEFINITION" in md_text
    assert "UNREACHABLE_CODE_AFTER_RETURN" in md_text
    assert "FORBIDDEN_LEGACY_PATTERN" in md_text
    assert "CROSS_FILE_CONSTANT_DRIFT" in md_text


def test_clean_slate_audit_passes_clean_deletion_and_replacement() -> None:
    clean_diff = (
        "diff --git a/service.py b/service.py\n"
        "index 1111111..3333333 100644\n"
        "--- a/service.py\n"
        "+++ b/service.py\n"
        "@@ -10,4 +10,2 @@\n"
        "-    raw = price * 100\n"
        "-    if discount:\n"
        "-        raw = raw - discount\n"
        "-    return raw / 100\n"
        "+    net_cents = round(price * 100) - round(discount * 100)\n"
        "+    return max(0, net_cents) / 100\n"
    )
    assert clean_slate_audit.audit_diff_text(clean_diff, mode="bugfix") == []


def test_sync_integrations_and_universal_installer_simulation(tmp_path: Path) -> None:
    # Simulate a fresh GitHub clone WITHOUT mcp_config.json and WITHOUT passing --project
    fresh_clone = tmp_path / "FreshClone"
    fresh_clone.mkdir()
    for item in ("plugin.json", "install.py", "README.md", "assets", "rules", "skills", "scripts"):
        src = FORGE_ROOT / item
        dst = fresh_clone / item
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    fake_gemini = tmp_path / "gemini_cfg"
    install_res = installer.run_installer(
        forge_root=fresh_clone,
        projects=[],
        gemini_config_dir=fake_gemini,
        auto_install_npm=False,
        node_bin_override="/usr/bin/node",
        trail_js_override="/usr/lib/node_modules/@trailhq/trail-code/dist/bin/trail.js",
    )
    assert install_res["installed"] is True
    assert install_res["registered_mcp_servers"] == ["cofi_trail_auto"]
    plugin_mcp = json.loads((fake_gemini / "plugins" / "cofi-vibe-forge" / "mcp_config.json").read_text(encoding="utf-8"))
    global_mcp = json.loads((fake_gemini / "mcp_config.json").read_text(encoding="utf-8"))
    assert "cofi_trail_auto" in plugin_mcp["mcpServers"]
    assert "cofi_trail_auto" in global_mcp["mcpServers"]
    assert (fake_gemini / "plugins" / "cofi-vibe-forge" / "scripts" / "auto_trail_mcp.py").is_file()

    # Re-syncing fresh_clone must preserve generated plugin mcp_config.json
    fake_ws = tmp_path / "ws_agents"
    fake_ws.mkdir()
    sync_integrations.sync_antigravity(
        forge_root=fresh_clone,
        gemini_config_dir=fake_gemini,
        workspace_agents_dir=fake_ws,
    )
    assert (fake_gemini / "plugins" / "cofi-vibe-forge" / "mcp_config.json").is_file()

    fake_doc = tmp_path / "FakeCofiDoc"
    qa_dir = fake_doc / "agents" / "quality_and_engineering"
    qa_dir.mkdir(parents=True)
    (qa_dir / "debug.md").write_bytes(b"---\nid: debug\nskills: none\n---\n\nBody\n")
    (qa_dir / "dev.md").write_bytes(b"---\nid: dev\nskills: none\n---\r\n\r\nBody\r\n")

    res_doc = sync_integrations.sync_cofi_documentary(
        forge_root=fresh_clone,
        cofi_doc_root=fake_doc,
        run_sync_script=False,
    )
    assert any("updated (debug.md" in a for a in res_doc["actions"])
    assert any("updated (dev.md" in a for a in res_doc["actions"])

    status = sync_integrations.inspect_status(
        forge_root=fresh_clone,
        gemini_config_dir=fake_gemini,
        workspace_agents_dir=fake_ws,
        cofi_doc_root=fake_doc,
    )
    assert status["antigravity_global_plugin_in_sync"] is True
    assert status["trail_mcp_servers_in_sync"] is True


def test_auto_trail_mcp_live_on_plain_folder_without_git() -> None:
    import tempfile

    # Plain standalone directory outside any Git repo (ZERO .git, ZERO pre-built .trail/graft index!)
    with tempfile.TemporaryDirectory() as raw_td:
        plain_dir = Path(raw_td) / "standalone_code"
        plain_dir.mkdir()
        code_file = plain_dir / "calc.py"
        code_file.write_text(
            "def multiply_values(x: int, y: int) -> int:\n"
            "    return x * y\n\n"
            "def compute_area(w: int, h: int) -> int:\n"
            "    return multiply_values(w, h)\n",
            encoding="utf-8",
        )

        mcp_script = FORGE_ROOT / "scripts" / "auto_trail_mcp.py"
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        proc = subprocess.Popen(
            [sys.executable, str(mcp_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "trail_file_api", "arguments": {"file": str(code_file)}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "trail_trace_calls", "arguments": {"symbol": "multiply_values", "dir": str(plain_dir)}}},
        ]
        out, err = proc.communicate("\n".join(json.dumps(r) for r in requests) + "\n", timeout=15)
        assert proc.returncode == 0, f"STDERR: {err}"
        lines = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 3
        skel_text = lines[1]["result"]["content"][0]["text"]
        callers_text = lines[2]["result"]["content"][0]["text"]
        assert "multiply_values" in skel_text and "compute_area" in skel_text
        assert "compute_area" in callers_text

