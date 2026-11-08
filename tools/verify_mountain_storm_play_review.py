"""New immutable saved-weather review with physical-time playback controls."""

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from tools.verify_mountain_source_adapter import write_json
from tools import verify_mountain_storm_review as review
from tools.verify_mountain_storm_60m import audit_playback


def export(destination):
    original_page = review.PAGE
    page = original_page.replace('<input id="time"',
        '<button id="play" type="button">播放</button><input id="time"')
    page = page.replace("document.getElementById('case').onchange=render;", """
let playbackTimer=null;
function pausePlayback(){if(playbackTimer!==null){clearInterval(playbackTimer);playbackTimer=null}document.getElementById('play').textContent='播放'}
document.getElementById('play').onclick=()=>{if(playbackTimer!==null){pausePlayback();return}const slider=document.getElementById('time');if(+slider.value>=+slider.max)slider.value=0;document.getElementById('play').textContent='暂停';render();playbackTimer=setInterval(()=>{slider.value=Math.min(+slider.max,+slider.value+1);render();if(+slider.value>=+slider.max)pausePlayback()},150)};
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePlayback()});
document.getElementById('case').onchange=render;"""
    )
    review.PAGE = page
    try:
        review.export_review(destination)
        review.browser_audit(destination)
        audit_playback(destination)
        write_json(destination / "freeze-manifest.json", {"status": "static_playback_frozen",
            "files_sha256": {path.name: file_sha256(path) for path in destination.iterdir() if path.is_file()},
            "exporter_sha256": file_sha256(Path(__file__)), "no_generation": True})
    finally:
        review.PAGE = original_page


if __name__ == "__main__":
    destination = ROOT / "verification/mountain-storm-play-review" / (
        "run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    export(destination)
    print(destination)
