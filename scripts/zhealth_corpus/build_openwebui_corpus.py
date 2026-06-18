#!/usr/bin/env python3
"""Build a chapter/episode/topic corpus from hivemind-stt artifacts.

The source tree under /Volumes/Public/ZHealth contains many files per video:
media, raw transcripts, VTT/SRT captions, manifest metadata, speaker maps, and
verbose JSON segment data. This script picks the best transcript artifact for
each episode and emits deterministic Markdown files ready for Open WebUI
knowledge sync.

No model API keys are used here. Topic splitting is deterministic and based on
STT segment timing/word counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = Path("/Volumes/Public/ZHealth")
DEFAULT_OUTPUT = DEFAULT_SOURCE / ".hivemind" / "openwebui-corpus"

TRANSCRIPT_SUFFIXES = [
    ".smoothed.named.verbose.json",
    ".smoothed.verbose.json",
    ".verbose.json",
    ".smoothed.named.txt",
    ".smoothed.txt",
    ".txt",
]

MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mp3", ".aac", ".wav"}

STOPWORDS = {
    "about",
    "after",
    "again",
    "all",
    "also",
    "and",
    "are",
    "because",
    "been",
    "being",
    "but",
    "can",
    "could",
    "did",
    "does",
    "doing",
    "don",
    "for",
    "from",
    "get",
    "going",
    "got",
    "had",
    "has",
    "have",
    "here",
    "how",
    "into",
    "its",
    "just",
    "kind",
    "know",
    "like",
    "little",
    "lot",
    "more",
    "now",
    "okay",
    "one",
    "our",
    "out",
    "right",
    "see",
    "should",
    "some",
    "that",
    "the",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "want",
    "was",
    "way",
    "really",
    "very",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "yeah",
    "you",
    "your",
}


@dataclass
class Segment:
    start: float | None
    end: float | None
    text: str
    speaker: str | None = None


@dataclass
class Episode:
    course: str
    chapter: str
    title: str
    stem: str
    source_path: Path
    transcript_path: Path
    media_path: Path | None
    manifest_path: Path | None
    speakers_path: Path | None
    segments: list[Segment]


def slugify(value: str, max_len: int = 80) -> str:
    value = value.strip().lower()
    value = re.sub(r"['’]", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return (value[:max_len].strip("-") or "untitled")


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower())


def format_ts(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def strip_transcript_suffix(path: Path) -> str | None:
    name = path.name
    for suffix in TRANSCRIPT_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def transcript_rank(path: Path) -> int:
    for idx, suffix in enumerate(TRANSCRIPT_SUFFIXES):
        if path.name.endswith(suffix):
            return idx
    return len(TRANSCRIPT_SUFFIXES)


def chapter_for_path(root: Path, path: Path) -> tuple[str, str]:
    rel = path.relative_to(root)
    course = rel.parts[0] if len(rel.parts) > 0 else "ZHealth"
    if len(rel.parts) > 2:
        chapter = rel.parts[1]
    else:
        chapter = "General"
    return course, chapter


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_segments(path: Path) -> list[Segment]:
    if path.suffix == ".json":
        data = load_json(path) or {}
        raw_segments = data.get("segments") or []
        segments = []
        for idx, item in enumerate(raw_segments):
            text = clean_text(str(item.get("text") or ""))
            if not text:
                continue
            segments.append(
                Segment(
                    start=_float_or_none(item.get("start")),
                    end=_float_or_none(item.get("end")),
                    text=text,
                    speaker=item.get("speaker") or item.get("speaker_id"),
                )
            )
        if segments:
            return segments
        text = clean_text(str(data.get("text") or ""))
        return [Segment(start=None, end=None, text=text)] if text else []

    text = path.read_text(encoding="utf-8", errors="ignore")
    text = clean_text(text)
    return [Segment(start=None, end=None, text=text)] if text else []


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def artifact_key(path: Path, stem: str) -> str:
    return str(path.parent / stem)


def iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".hivemind"]
        for filename in filenames:
            yield Path(dirpath) / filename


def discover_episodes(root: Path, limit: int | None = None) -> list[Episode]:
    candidates: dict[str, list[Path]] = defaultdict(list)
    media_by_key: dict[str, Path] = {}
    manifest_by_key: dict[str, Path] = {}
    speakers_by_key: dict[str, Path] = {}

    for path in iter_source_files(root):
        stem = strip_transcript_suffix(path)
        if stem is not None:
            key = artifact_key(path, stem)
            candidates[key].append(path)
            continue

        if path.suffix.lower() in MEDIA_EXTENSIONS:
            media_by_key.setdefault(artifact_key(path, path.stem), path)
        elif path.name.endswith(".manifest.json"):
            manifest_by_key.setdefault(artifact_key(path, path.name[: -len(".manifest.json")]), path)
        elif path.name.endswith(".speakers.json"):
            speakers_by_key.setdefault(artifact_key(path, path.name[: -len(".speakers.json")]), path)

    episodes = []
    total = len(candidates)
    for idx, (key, transcript_paths) in enumerate(sorted(candidates.items()), start=1):
        stem = Path(key).name
        transcript_path = None
        segments = []
        for candidate_path in sorted(transcript_paths, key=transcript_rank):
            candidate_segments = load_segments(candidate_path)
            if candidate_segments:
                transcript_path = candidate_path
                segments = candidate_segments
                break
        if transcript_path is None:
            continue
        course, chapter = chapter_for_path(root, transcript_path)
        episodes.append(
            Episode(
                course=course,
                chapter=chapter,
                title=stem,
                stem=stem,
                source_path=Path(key),
                transcript_path=transcript_path,
                media_path=media_by_key.get(key),
                manifest_path=manifest_by_key.get(key),
                speakers_path=speakers_by_key.get(key),
                segments=segments,
            )
        )
        if idx % 50 == 0:
            print(f"Loaded {idx}/{total} transcript artifacts...", flush=True)
        if limit and len(episodes) >= limit:
            break
    return episodes


def split_topics(
    segments: list[Segment],
    target_words: int,
    max_seconds: int,
) -> list[list[Segment]]:
    topics: list[list[Segment]] = []
    current: list[Segment] = []
    current_words = 0
    start_time: float | None = None

    for segment in segments:
        if not current:
            start_time = segment.start
        current.append(segment)
        current_words += len(words(segment.text))

        elapsed = None
        if start_time is not None and segment.end is not None:
            elapsed = segment.end - start_time

        ends_cleanly = bool(re.search(r"[.!?][\"')\]]?$", segment.text))
        if current_words >= target_words and (ends_cleanly or (elapsed and elapsed >= max_seconds)):
            topics.append(current)
            current = []
            current_words = 0
            start_time = None
        elif elapsed and elapsed >= max_seconds:
            topics.append(current)
            current = []
            current_words = 0
            start_time = None

    if current:
        topics.append(current)

    return topics


def topic_label(topic_segments: list[Segment], fallback: str) -> str:
    text = " ".join(segment.text for segment in topic_segments)
    counts = Counter(w for w in words(text) if w not in STOPWORDS and len(w) > 3)
    terms = [term for term, _ in counts.most_common(4)]
    if terms:
        return " / ".join(term.title() for term in terms)
    sentence = re.split(r"(?<=[.!?])\s+", text)[0]
    return clean_text(sentence[:80]) or fallback


def stable_id(*parts: str) -> str:
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:24]


def render_topic_markdown(
    episode: Episode,
    topic_segments: list[Segment],
    topic_index: int,
    topic_count: int,
    label: str,
) -> str:
    start = next((s.start for s in topic_segments if s.start is not None), None)
    end = next((s.end for s in reversed(topic_segments) if s.end is not None), None)
    topic_id = stable_id(episode.course, episode.chapter, episode.stem, str(topic_index), label)
    episode_id = stable_id(episode.course, episode.chapter, episode.stem)
    chapter_id = stable_id(episode.course, episode.chapter)
    body_lines = []
    previous_speaker = None
    paragraph = []

    def flush():
        if paragraph:
            body_lines.append(" ".join(paragraph).strip())
            paragraph.clear()

    for segment in topic_segments:
        speaker = segment.speaker
        prefix = ""
        if speaker and speaker != previous_speaker:
            flush()
            prefix = f"**{speaker}:** "
            previous_speaker = speaker
        paragraph.append(prefix + segment.text)
    flush()

    transcript = "\n\n".join(body_lines)
    source_media = str(episode.media_path) if episode.media_path else ""
    source_manifest = str(episode.manifest_path) if episode.manifest_path else ""

    return f"""---
corpus: zhealth
source_system: hivemind-stt
course: {json.dumps(episode.course)}
chapter: {json.dumps(episode.chapter)}
episode: {json.dumps(episode.title)}
topic: {json.dumps(label)}
chapter_id: {chapter_id}
episode_id: {episode_id}
topic_id: {topic_id}
topic_index: {topic_index}
topic_count: {topic_count}
start_time: {format_ts(start)}
end_time: {format_ts(end)}
source_transcript: {json.dumps(str(episode.transcript_path))}
source_media: {json.dumps(source_media)}
source_manifest: {json.dumps(source_manifest)}
---

# {episode.course} / {episode.chapter}

## {episode.title}

### Topic {topic_index:02d}: {label}

- Time range: {format_ts(start)} - {format_ts(end)}
- Source transcript: `{episode.transcript_path}`
{f"- Source media: `{episode.media_path}`" if episode.media_path else "- Source media: unavailable"}

{transcript}
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(root: Path, output: Path, target_words: int, max_seconds: int, limit: int | None) -> dict[str, Any]:
    episodes = discover_episodes(root, limit=limit)
    generated_files = []
    groups: dict[str, dict[str, Any]] = {}
    episode_dir_sources: dict[str, Path] = {}

    for episode in episodes:
        topics = split_topics(episode.segments, target_words=target_words, max_seconds=max_seconds)
        course_slug = slugify(episode.course)
        chapter_slug = slugify(episode.chapter)
        episode_slug = slugify(episode.title)
        episode_dir_key = f"{course_slug}/{chapter_slug}/{episode_slug}"
        existing_source = episode_dir_sources.get(episode_dir_key)
        if existing_source and existing_source != episode.source_path:
            episode_slug = f"{episode_slug}-{stable_id(str(episode.source_path))[:8]}"
            episode_dir_key = f"{course_slug}/{chapter_slug}/{episode_slug}"
        episode_dir_sources.setdefault(episode_dir_key, episode.source_path)
        group_key = f"{course_slug}/{chapter_slug}"
        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "knowledge_name": f"ZHealth / {episode.course} / {episode.chapter}",
                "description": (
                    f"ZHealth hivemind-stt transcript topics for course '{episode.course}', "
                    f"chapter '{episode.chapter}'."
                ),
                "manifest": [],
            },
        )

        for idx, topic_segments in enumerate(topics, start=1):
            label = topic_label(topic_segments, fallback=f"Topic {idx}")
            filename = f"{idx:03d}-{slugify(label, 60)}.md"
            relative_dir = Path(course_slug) / chapter_slug / episode_slug
            out_path = output / relative_dir / filename
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                render_topic_markdown(episode, topic_segments, idx, len(topics), label),
                encoding="utf-8",
            )
            checksum = sha256_file(out_path)
            item = {
                "filename": filename,
                "path": str(relative_dir),
                "checksum": checksum,
                "size": out_path.stat().st_size,
                "local_path": str(out_path),
                "course": episode.course,
                "chapter": episode.chapter,
                "episode": episode.title,
                "topic": label,
                "topic_index": idx,
                "topic_count": len(topics),
                "source_transcript": str(episode.transcript_path),
                "source_media": str(episode.media_path) if episode.media_path else None,
            }
            group["manifest"].append({k: item[k] for k in ("filename", "path", "checksum", "size")})
            generated_files.append(item)

    manifest = {
        "source_root": str(root),
        "output_root": str(output),
        "builder": "scripts/zhealth_corpus/build_openwebui_corpus.py",
        "topic_policy": {
            "target_words": target_words,
            "max_seconds": max_seconds,
        },
        "episode_count": len(episodes),
        "file_count": len(generated_files),
        "groups": sorted(groups.values(), key=lambda g: g["key"]),
        "files": generated_files,
    }
    write_json(output / "openwebui-sync-manifest.json", manifest)

    by_group = defaultdict(list)
    for file_info in generated_files:
        by_group[f"{slugify(file_info['course'])}/{slugify(file_info['chapter'])}"].append(file_info)
    for group_key, items in by_group.items():
        write_json(output / group_key / "manifest.json", items)

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-words", type=int, default=850)
    parser.add_argument("--max-seconds", type=int, default=540)
    parser.add_argument("--limit", type=int, default=None, help="Limit episodes for testing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build(
        root=args.source.resolve(),
        output=args.output.resolve(),
        target_words=args.target_words,
        max_seconds=args.max_seconds,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "output_root": manifest["output_root"],
                "episode_count": manifest["episode_count"],
                "file_count": manifest["file_count"],
                "group_count": len(manifest["groups"]),
                "manifest": str(Path(manifest["output_root"]) / "openwebui-sync-manifest.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
