"""Settings API for an employee's local meeting-folder watcher."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from meetings.models import MeetingWatchSetting
from meetings.watch_control import alive, allowed_root, ensure_process, validate_folder
from projects.models import Project


def payload(control):
    return {
        'enabled': control.enabled,
        'running': alive(control.process_id),
        'project_id': control.project_id,
        'folder': control.folder,
        'folder_available': bool(allowed_root() and allowed_root().is_dir()),
        'last_error': control.last_error,
        'heartbeat_at': control.heartbeat_at,
    }


class MeetingWatchControlView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        control, _ = MeetingWatchSetting.objects.get_or_create(user=request.user)
        if control.enabled and not alive(control.process_id):
            try:
                control = ensure_process(control.pk)
            except Exception as exc:
                control.last_error = str(exc)[:1000]
                control.save(update_fields=['last_error', 'updated_at'])
        return Response(payload(control))

    def patch(self, request):
        control, _ = MeetingWatchSetting.objects.get_or_create(user=request.user)
        if control.enabled:
            return Response({'error': '감시를 끈 뒤 폴더를 변경하세요.'}, status=409)
        try:
            folder = validate_folder(request.data.get('folder'))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        control.folder = str(folder)
        control.last_error = ''
        control.save(update_fields=['folder', 'last_error', 'updated_at'])
        return Response(payload(control))

    def post(self, request):
        enabled = request.data.get('enabled')
        if type(enabled) is not bool:
            return Response({'error': 'enabled는 true 또는 false여야 합니다.'}, status=400)
        control, _ = MeetingWatchSetting.objects.get_or_create(user=request.user)
        if not enabled:
            control.enabled = False
            control.save(update_fields=['enabled', 'updated_at'])
            return Response(payload(control))
        try:
            folder = validate_folder(request.data.get('folder'))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        try:
            project_id = int(request.data.get('project_id'))
        except (TypeError, ValueError):
            return Response({'error': '프로젝트를 선택하세요.'}, status=400)
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({'error': '프로젝트가 없습니다.'}, status=404)
        if not request.user.is_staff and project.owner_id != request.user.pk:
            return Response({'error': '프로젝트 소유자 또는 PM만 켤 수 있습니다.'}, status=403)
        if control.enabled and (control.project_id != project_id or control.folder != str(folder)):
            return Response({'error': '감시를 끈 뒤 폴더나 프로젝트를 변경하세요.'}, status=409)
        control.enabled = True
        control.folder = str(folder)
        control.project = project
        control.last_error = ''
        control.save(update_fields=['enabled', 'folder', 'project', 'last_error', 'updated_at'])
        try:
            control = ensure_process(control.pk)
        except Exception as exc:
            control.enabled = False
            control.last_error = str(exc)[:1000]
            control.save(update_fields=['enabled', 'last_error', 'updated_at'])
            return Response({'error': f'감시 프로세스를 시작하지 못했습니다: {exc}'}, status=500)
        return Response(payload(control))
