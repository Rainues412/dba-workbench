"""Extract a version's reviewed changelog for GitHub Releases."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


def release_notes(changelog: str, version: str, repository: str, *, sha256: str | None = None, assets: bool = True) -> str:
    version = version.removeprefix("v")
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Version must use v<major>.<minor>.<patch>.")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("Repository must use owner/name.")
    headings = list(re.finditer(r"^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})\s*$", changelog, re.MULTILINE))
    matching = [index for index, heading in enumerate(headings) if heading[1] == version]
    if len(matching) != 1:
        raise ValueError(f"Expected one CHANGELOG.md entry for {version}; found {len(matching)}.")
    index = matching[0]
    heading = headings[index]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
    body = changelog[heading.end():end].strip()
    if not body:
        raise ValueError(f"Changelog entry for {version} is empty.")
    result = f"## {version} - {heading[2]}\n\n{body}\n"
    if assets:
        filename = f"DBA-Workbench-Setup-{version}-x64.exe"
        base = f"https://github.com/{repository}/releases/download/v{version}/{filename}"
        result += (
            "\n---\n\n### 下载与安装\n\n"
            "| 平台 | 安装程序 | 校验文件 |\n| --- | --- | --- |\n"
            f"| Windows 10/11 x64 | [下载安装程序]({base}) | [SHA-256]({base}.sha256) |\n\n"
            "下载 EXE 后双击安装，可选择安装目录和桌面快捷方式。请先退出正在运行的工作台，再覆盖安装。\n\n"
            "校验安装包：\n\n```powershell\n"
            f"Get-FileHash '.\\{filename}' -Algorithm SHA256\n```\n\n"
            "将结果与同名 `.sha256` 文件中的值核对一致后再安装。\n"
        )
    if sha256:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            raise ValueError("SHA-256 must contain 64 hexadecimal characters.")
        result += f"\n本次发布安装包 SHA-256：\n\n```text\n{sha256.upper()}\n```\n"
    result += f"\n[完整更新日志](https://github.com/{repository}/blob/main/CHANGELOG.md) · [所有版本](https://github.com/{repository}/releases)\n"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--changelog", type=Path, default=Path(__file__).resolve().parents[1] / "CHANGELOG.md")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256")
    parser.add_argument("--no-assets", action="store_true", help="Historical tags without retained installer assets")
    args = parser.parse_args()
    try:
        notes = release_notes(args.changelog.read_text(encoding="utf-8-sig"), args.version, args.repository, sha256=args.sha256, assets=not args.no_assets)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
