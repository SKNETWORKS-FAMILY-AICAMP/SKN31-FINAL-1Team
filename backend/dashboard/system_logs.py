"""Bounded, PM-only view of the configured Django application log."""
import re
from pathlib import Path

from django.conf import settings
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsPMUser

MAX_BYTES = 128 * 1024
MAX_LINES = 250
SECRET_PATTERNS = (
    re.compile(r'(?i)(authorization\s*[:=]\s*bearer\s+)\S+'),
    re.compile(r'(?i)\b(sk-[A-Za-z0-9_-]{12,})\b'),
    re.compile(r'(?i)((?:api[_-]?key|password|secret|token|cookie)\s*[:=]\s*)[^\s,;]+'),
)


def redact(line: str) -> str:
    line = SECRET_PATTERNS[0].sub(r'\1[REDACTED]', line)
    line = SECRET_PATTERNS[1].sub('[REDACTED]', line)
    line = SECRET_PATTERNS[2].sub(r'\1[REDACTED]', line)
    return line


def tail_log(path: Path) -> tuple[list[str], bool]:
    if not path.is_file():
        return [], False
    with path.open('rb') as handle:
        handle.seek(0, 2)
        size = handle.tell()
        offset = max(0, size - MAX_BYTES)
        handle.seek(offset)
        raw = handle.read(MAX_BYTES)
    text = raw.decode('utf-8', errors='replace')
    lines = text.splitlines()
    if offset and lines:
        lines = lines[1:]  # The first line may be an incomplete traceback line.
    clipped = offset > 0 or len(lines) > MAX_LINES
    return [redact(line) for line in lines[-MAX_LINES:]], clipped


class DashboardSystemLogsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    def get(self, request):
        path = settings.BASE_DIR / 'logs' / 'django.log'
        lines, truncated = tail_log(path)
        return Response({'lines': lines, 'truncated': truncated, 'available': path.is_file()})
