# specs/tasks.py
import os
from openai import OpenAI
from .models import SpecDocument
from meetings.models import MeetingNote

def generate_spec_from_meeting(meeting_id: int):
    """
    회의록 데이터를 바탕으로 기획서를 자동 생성하는 백그라운드 함수
    """
    try:
        meeting = MeetingNote.objects.get(id=meeting_id)
        spec, created = SpecDocument.objects.get_or_create(
            meeting=meeting,
            defaults={
                'title': f"[기획서] {meeting.title}",
                'status': SpecDocument.Status.GENERATING
            }
        )
        
        # OpenAI API 호출 (필요 시 연동)
        # client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # response = client.chat.completions.create(...)
        
        # 기획서 생성 완료 처리
        spec.summary = f"회의록 '{meeting.title}' 기반으로 생성된 기획서 요약 내용입니다."
        spec.status = SpecDocument.Status.COMPLETED
        spec.save()

    except MeetingNote.DoesNotExist:
        pass