"""Run once and exit; scheduling belongs to the hosting platform."""

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.scraper import scrape
from src.uploader import sync_articles

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def load_local_articles(data_dir: Path, limit: int = 0) -> list[dict]:
    paths = sorted(path for path in (data_dir / 'articles').glob('*.md')
                   if path.is_file() and not path.is_symlink())
    if limit:
        paths = paths[:limit]
    if not paths:
        raise ValueError('No local Markdown articles found. Run --scrape-only first.')
    rows = []
    for path in paths:
        content = path.read_text(encoding='utf-8')
        url = next((line.removeprefix('Article URL:').strip() for line in content.splitlines()
                    if line.startswith('Article URL:')), '')
        if not url:
            raise ValueError(f'{path.name} is missing Article URL:.')
        rows.append(dict(id=path.stem, filename=path.name, url=url,
                         title=content.splitlines()[0].lstrip('# ').strip(),
                         sha256=hashlib.sha256(content.encode('utf-8')).hexdigest()))
    return rows


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--scrape-only", action="store_true", help="Download articles without uploading")
    modes.add_argument("--upload-only", action="store_true", help="Sync existing local Markdown files without scraping")
    parser.add_argument("--limit", type=int, default=0, help="Maximum articles selected; 0 = all. Upload-only uses filename order.")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = Path(os.getenv("LOG_DIR", "logs"))
    logs_dir.mkdir(parents=True, exist_ok=True)
    mode = 'upload' if args.upload_only else ('scrape' if args.scrape_only else 'sync')
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "mode": mode}
    try:
        if args.upload_only:
            rows = load_local_articles(data_dir, args.limit)
            result['selected'] = len(rows)
        else:
            rows = scrape(data_dir, args.limit)
            result["scraped"] = len(rows)
        if not args.scrape_only:
            result.update(sync_articles(rows, data_dir))
        result["status"] = "success"
        return_code = 0
    except Exception as exc:
        logging.exception("Run failed")
        result.update(status="failed", error=str(exc))
        return_code = 1
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    (logs_dir / "last-run.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
