from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_uninstaller_preserves_data_by_default_and_only_deletes_exact_app_directory() -> None:
    script = (REPO_ROOT / "packaging" / "windows" / "installer.iss").read_text(encoding="utf-8")

    assert "procedure CurUninstallStepChanged" in script
    assert "MB_YESNO or MB_DEFBUTTON2, IDNO" in script
    assert "ExpandConstant('{localappdata}\\DBA Workbench')" in script
    assert "DelTree(DataDirectory, True, True, True)" in script
    assert "数据库、密码保险箱恢复密钥、日志和目录授权配置" in script
