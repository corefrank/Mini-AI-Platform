"""从已核对的官方 GitHub commit 下载正文。Python 标准库即可运行。"""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def normalize(raw, suffix):
    raw = raw.replace("\r\n", "\n")
    if suffix in {".md", ".mdx"}:
        raw = re.sub(r"\A---[ \t]*\n.*?\n---[ \t]*\n", "", raw, count=1, flags=re.S)
    if suffix == ".mdx":
        raw = re.sub(r"(?m)^(import|export) [^\n]+\n", "", raw)
        raw = re.sub(r"(?m)^\s*</?(?:Note|Tip|Warning|Info|Tabs|Tab|Accordion|AccordionGroup)(?:\s+[^<>]*)?>\s*$",
                     "", raw)
    # RST 保留标题、段落、代码和指令原样，作为纯文本索引。
    return raw.strip() + "\n"


def fetch(entry, catalog, output):
    source = catalog[entry["category"]]
    track = f'{source["repository"]}/{source["revision"]}/{entry["path"]}'
    raw_url = f"https://raw.githubusercontent.com/{track}"
    with urlopen(Request(raw_url, headers={"User-Agent": "mini-ai-platform-corpus/1.0"}),
                 timeout=35) as response:
        raw = response.read().decode("utf-8-sig")
    content = normalize(raw, Path(entry["path"]).suffix)
    if not content.strip() or len(content.encode("utf-8")) > 512 * 1024:
        raise ValueError("正文为空或超出上传上限")
    filename = entry["document_id"] + (".txt" if entry["path"].endswith(".rst") else ".md")
    (output / filename).write_text(content, encoding="utf-8", newline="\n")
    return {**entry, "filename": filename, "raw_url": raw_url, "revision": source["revision"],
            "retrieved_on": date.today().isoformat(), "license": source["license"],
            "license_url": source["license_url"], "sha256": hashlib.sha256(content.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="每个类别最多下载 N 篇，0 表示全部")
    parser.add_argument("--output", type=Path, default=DATA / "documents")
    args = parser.parse_args()
    source_list = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    catalog = {item["category"]: item for item in source_list["sources"]}
    counts = dict.fromkeys(catalog, 0)
    selected = []
    for item in source_list["documents"]:
        category = item["category"]
        if not args.limit or counts[category] < args.limit:
            selected.append(item)
            counts[category] += 1
    args.output.mkdir(parents=True, exist_ok=True)
    downloaded, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        work = [(item, pool.submit(fetch, item, catalog, args.output)) for item in selected]
        for item, future in work:
            try:
                downloaded.append(future.result())
            except (OSError, ValueError) as exc:
                errors.append(f'{item["document_id"]}: {exc}')
    (args.output / "manifest.json").write_text(json.dumps(downloaded, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(f"Downloaded {len(downloaded)}/{len(selected)} documents")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
