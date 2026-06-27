from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _image_holders(data: list[dict[str, Any]]):
    for result in data:
        for question in result.get("questions", []):
            yield question
            yield from question.get("answers", [])
            answer_given = question.get("answer_given")
            if answer_given:
                yield answer_given
            yield from question.get("accepted_answers", [])


def collect_image_urls(data: list[dict[str, Any]]) -> list[str]:
    urls: set[str] = set()
    for holder in _image_holders(data):
        source_images = holder.get("source_images", holder.get("images", []))
        urls.update(url for url in source_images if url.startswith(("http://", "https://")))
    return sorted(urls)


def local_name(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    if not name or name in {".", ".."}:
        raise ValueError(f"Image URL has no filename: {url}")
    return name


def download_one(url: str, destination: Path, retries: int = 3) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error: Exception | None = None
    for attempt in range(retries):
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    raise ValueError(f"Unexpected content type {content_type}")
                content = response.read()
            if not content:
                raise ValueError("Empty response")
            temporary.write_bytes(content)
            temporary.replace(destination)
            return
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Could not download {url}: {last_error}")


def update_local_paths(data: list[dict[str, Any]], mapping: dict[str, str]) -> None:
    for holder in _image_holders(data):
        source_images = holder.get("source_images", holder.get("images", []))
        if not source_images:
            continue
        holder["source_images"] = source_images
        holder["images"] = [mapping.get(url, url) for url in source_images]
        html = holder.get("html")
        if isinstance(html, str):
            for source, local in mapping.items():
                if source in html:
                    html = html.replace(source, local)
            holder["html"] = html


def main() -> None:
    parser = argparse.ArgumentParser(description="Download images referenced by crawled results")
    parser.add_argument("--input", default="output/classmarker_questions.json")
    parser.add_argument("--images-dir", default="output/images")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    input_path = Path(args.input)
    images_dir = Path(args.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    urls = collect_image_urls(data)
    mapping = {url: f"images/{local_name(url)}" for url in urls}
    failures: dict[str, str] = {}

    def task(url: str) -> None:
        download_one(url, images_dir / local_name(url))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(task, url): url for url in urls}
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            url = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures[url] = str(exc)
            if index % 50 == 0 or index == len(urls):
                print(f"[{index}/{len(urls)}] downloaded, {len(failures)} failure(s)", flush=True)

    successful_mapping = {url: path for url, path in mapping.items() if url not in failures}
    update_local_paths(data, successful_mapping)
    temporary = input_path.with_suffix(input_path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(input_path)

    if failures:
        failure_path = images_dir / "download_failures.json"
        failure_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"Finished with {len(failures)} failure(s); see {failure_path}")
    print(f"Done: {len(urls)} image(s), output={images_dir}")


if __name__ == "__main__":
    main()
