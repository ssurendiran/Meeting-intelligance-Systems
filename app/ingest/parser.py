import re
import io
from dataclasses import dataclass
from typing import Iterable, Iterator, List


LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*([^:]{1,60}):\s*(.+)$")


@dataclass
class Turn:
    """A single spoken line from a transcript: line number, timestamp, speaker name, text, and raw line string.
    Why available: Standard unit for parsing; consumed by chunker and meeting_stats."""

    line_no: int
    timestamp: str
    speaker: str
    text: str
    raw: str


def parse_transcript_stream(lines: Iterable[str]) -> Iterator[Turn]:
    """Streaming transcript parser: consumes an iterable of lines and yields Turn objects incrementally (does not load whole file).
    Why available: Used at ingest so large transcripts can be parsed and chunked without loading the entire file into memory."""
    current: Turn | None = None

    for idx, line in enumerate(lines, start=1):
        line = line.rstrip("\n")
        if not line.strip():
            continue

        m = LINE_RE.match(line.strip())
        if m:
            # flush previous
            if current is not None:
                yield current

            ts, speaker, msg = m.group(1), m.group(2).strip(), m.group(3).strip()
            current = Turn(
                line_no=idx,
                timestamp=ts,
                speaker=speaker,
                text=msg,
                raw=line,
            )
        else:
            # continuation line -> attach to current if exists
            if current is not None:
                current.text += " " + line.strip()
                current.raw += "\n" + line
            else:
                # orphan line -> create synthetic first turn
                current = Turn(
                    line_no=idx,
                    timestamp="00:00:00",
                    speaker="Unknown",
                    text=line.strip(),
                    raw=line,
                )

    if current is not None:
        yield current


def parse_transcript(text: str) -> List[Turn]:
    """
    Backward compatible non-streaming API.
    Keeps existing callers working.
    """
    return list(parse_transcript_stream(io.StringIO(text)))


def has_valid_transcript_format(text: str) -> bool:
    """Return True if the text has at least one line matching [HH:MM:SS] Speaker: text.
    Why available: Used to reject uploads that are not in the expected transcript format before ingest."""
    if not (text or "").strip():
        return False
    for line in text.splitlines():
        if LINE_RE.match(line.strip()):
            return True
    return False
