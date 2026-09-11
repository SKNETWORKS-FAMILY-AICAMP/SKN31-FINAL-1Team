from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile

UPLOAD_MAX_BYTES = 200 * 1024 * 1024
API_MAX_BYTES = 24_000_000

@contextmanager
def audio_parts(upload):
    if not upload.size or upload.size > UPLOAD_MAX_BYTES:
        raise ValueError("음성 파일은 0바이트 초과, 200MB 이하여야 합니다.")
    upload.seek(0)
    if upload.size <= API_MAX_BYTES:
        yield [(upload.name, upload.read(), upload.content_type or "application/octet-stream")]
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("대용량 음성 처리에는 서버에 FFmpeg 설치 및 PATH 설정이 필요합니다.")
    with tempfile.TemporaryDirectory(prefix="meeting-audio-") as temp:
        folder = Path(temp)
        source = folder / ("source" + Path(upload.name).suffix.lower())
        with source.open("wb") as target:
            for chunk in upload.chunks():
                target.write(chunk)
        try:
            subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "libmp3lame", "-b:a", "64k", "-f", "segment", "-segment_time", "600",
                "-reset_timestamps", "1", str(folder / "part-%06d.mp3")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("음성 압축·분할 시간이 초과되었습니다. 더 짧은 파일로 나누어 주세요.") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError("음성 파일을 읽을 수 없습니다. 오디오 트랙과 파일 손상 여부를 확인해 주세요.") from exc
        paths = sorted(folder.glob("part-*.mp3"))
        if not paths or any(p.stat().st_size == 0 or p.stat().st_size > API_MAX_BYTES for p in paths):
            raise ValueError("음성 파일을 API 허용 크기로 분할하지 못했습니다.")
        yield ((p.name, p.read_bytes(), "audio/mpeg") for p in paths)

def transcribe_upload(upload, client, *, keywords, prompt):
    texts = []
    with audio_parts(upload) as parts:
        for part in parts:
            context = prompt
            if texts:
                context += "\n이전 구간 문맥(반복 출력하지 마세요):\n" + texts[-1][-800:]
            result = client.audio.transcriptions.create(model="gpt-transcribe", file=part,
                keywords=keywords, prompt=context, temperature=0)
            texts.append((result.text or "").strip())
    return "\n\n".join(t for t in texts if t)
