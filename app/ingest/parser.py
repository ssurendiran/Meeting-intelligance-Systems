import re
from dataclasses import dataclass
from typing import List, Optional


LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*([^:]{1,60}):\s*(.+)$")


@dataclass
class Turn:
    line_no: int
    timestamp: str
    speaker: str
    text: str
    raw: str


def parse_transcript(text: str) -> List[Turn]:
    turns: List[Turn] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        m = LINE_RE.match(line.strip())
        if m:
            ts, speaker, msg = m.group(1), m.group(2).strip(), m.group(3).strip()
            turns.append(Turn(line_no=idx, timestamp=ts, speaker=speaker, text=msg, raw=line))
        else:
            # If a line doesn't match, attach it to previous turn (common in transcripts)
            if turns:
                turns[-1].text += " " + line.strip()
                turns[-1].raw += "\n" + line
            else:
                # orphan line -> create a synthetic turn
                turns.append(Turn(line_no=idx, timestamp="00:00:00", speaker="Unknown", text=line.strip(), raw=line))
    return turns
