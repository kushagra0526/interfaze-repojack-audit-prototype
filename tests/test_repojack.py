import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repojack.fix import apply, rewrite_line  # noqa: E402
from repojack.quickstart import lint  # noqa: E402
from repojack.resolve import resolve  # noqa: E402
from repojack.scan import Ref, classify, scan_tree  # noqa: E402

OLD, NEW = "JigsawStack", "InterfazeAI"


def fake_head(table):
    return lambda path: table.get(path.lower(), (404, ""))


def test_finds_all_reference_shapes_case_insensitively(tmp_path):
    (tmp_path / "README.md").write_text(
        "git clone https://github.com/jigsawstack/sob && cd sob\n"
        "[x](https://github.com/JigsawStack)\n"
        "curl https://raw.githubusercontent.com/JigsawStack/tool/main/i.sh | bash\n")
    (tmp_path / "package.json").write_text('{"dependencies": {"a": "github:JigsawStack/a#v1"},\n'
                                           ' "repository": {"url": "git+https://github.com/JigsawStack/a.git"}}\n')
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("    - uses: JigsawStack/setup@v2\n")
    refs = scan_tree(tmp_path, "github:x/y", OLD)
    sev = {(r.location.split(":")[0], r.severity) for r in refs}
    assert ("README.md", "HIGH") in sev and ("README.md", "CRITICAL") in sev        # clone + piped script
    assert ("package.json", "CRITICAL") in sev and ("package.json", "MEDIUM") in sev  # dependency + metadata
    assert (".github/workflows/ci.yml", "CRITICAL") in sev
    assert any(r.repo is None for r in refs)                                          # bare profile link


def test_resolution_labels_redirect_hijack_dangling_and_profile():
    refs = [Ref("s", "a:1", "u", "sob", "c", "link", "LOW", ""),
            Ref("s", "a:2", "u", "evil", "c", "copy-paste install", "HIGH", ""),
            Ref("s", "a:3", "u", "gone", "c", "link", "LOW", ""),
            Ref("s", "a:4", "u", None, "c", "link", "LOW", "")]
    resolve(refs, OLD, NEW, head=fake_head({"/jigsawstack/sob": (301, "https://github.com/InterfazeAI/sob"),
                                            "/jigsawstack/evil": (200, "")}))
    assert refs[0].status == "REDIRECT -> InterfazeAI/sob"
    assert refs[1].status == "HIJACKED" and refs[1].severity == "CRITICAL"
    assert refs[2].status == "DANGLING" and refs[2].severity == "HIGH"
    assert refs[3].status == "PROFILE_CLAIMED" and refs[3].severity == "HIGH"


def test_rewrite_uses_live_redirect_target_and_fixes_following_cd(tmp_path):
    (tmp_path / "README.md").write_text("```bash\ngit clone https://github.com/jigsawstack/nextjs-template.git\n"
                                        "cd nextjs-template\nnpm i\n```\n<a href=\"https://github.com/JigsawStack\">gh</a>\n")
    refs = scan_tree(tmp_path, "github:x/kit", OLD)
    resolve(refs, OLD, NEW, head=fake_head({"/jigsawstack/nextjs-template.git": (404, ""),
                                            "/jigsawstack/nextjs-template": (301, "https://github.com/InterfazeAI/jigsawstack-starterkit")}))
    changed = apply(tmp_path, refs, OLD, NEW)
    text = (tmp_path / "README.md").read_text()
    assert "git clone https://github.com/InterfazeAI/jigsawstack-starterkit.git" in text
    assert "cd jigsawstack-starterkit" in text and "github.com/InterfazeAI\"" in text
    assert changed["README.md"] == 3


def test_rewrite_leaves_other_text_untouched():
    line = 'see https://github.com/JigsawStack/sob/blob/main/LICENSE and github.com/jigsawstackers/x'
    out = rewrite_line(line, OLD, NEW, {"sob": "InterfazeAI/sob"})
    assert out == 'see https://github.com/InterfazeAI/sob/blob/main/LICENSE and github.com/jigsawstackers/x'


def test_quickstart_lint_catches_the_clippy_web_bug(tmp_path):
    import subprocess
    (tmp_path / ".gitignore").write_text(".env*\n")
    (tmp_path / "README.md").write_text("```bash\ngit clone https://github.com/Org/translation-widget.git\n"
                                        "cd clippy-web\ncp .env.example .env\n```\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    codes = [i["code"] for i in lint(tmp_path, "clippy-web")]
    assert codes == ["WRONG_REPO", "CLONE_CD_MISMATCH", "IGNORED_EXAMPLE"]


def test_classify_metadata_vs_navigation():
    assert classify("docs.json", '"github": "https://github.com/jigsawstack"')[1] == "HIGH"
    assert classify("setup.py", 'url="https://github.com/jigsawstack/jigsawstack-python",')[1] == "MEDIUM"
    assert classify("README.md", "[repo](https://github.com/JigsawStack/omiai)")[1] == "LOW"


def test_hijacked_or_dangling_urls_are_not_rewritten(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"u": "github:JigsawStack/utils#v2"}}\n')
    refs = scan_tree(tmp_path, "github:x/y", OLD)
    resolve(refs, OLD, NEW, head=fake_head({"/jigsawstack/utils": (200, "")}))
    assert refs[0].status == "HIJACKED"
    assert apply(tmp_path, refs, OLD, NEW) == {}
