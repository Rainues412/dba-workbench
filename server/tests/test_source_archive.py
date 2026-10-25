"""Exercise Git's actual archive export rules, including nested mixed-case names."""
import io
from pathlib import Path
import subprocess
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def test_source_archives_exclude_agent_rules_at_every_depth_and_case(tmp_path):
    attributes = (ROOT / ".gitattributes").read_bytes()
    (tmp_path / ".gitattributes").write_bytes(attributes)
    for name in ["AGENTS.md", "nested/agents.MD", "nested/deeper/AgEnTs.mD", "README.md", "nested/keep.txt"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic archive fixture", encoding="utf-8")
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True).stdout
    git("init", "--quiet")
    git("add", ".")
    tree = git("write-tree").decode().strip()
    for format in ["zip", "tar"]:
        archive = io.BytesIO(git("archive", f"--format={format}", tree))
        if format == "zip":
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
        else:
            with tarfile.open(fileobj=archive) as bundle:
                names = bundle.getnames()
        assert not any(Path(name).name.casefold() == "agents.md" for name in names), names
        assert "README.md" in names and "nested/keep.txt" in names
