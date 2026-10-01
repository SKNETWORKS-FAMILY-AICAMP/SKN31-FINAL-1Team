"""
chunk_meeting_text가 줄바꿈이 거의 없는 원문도 실제로 나누는지 검사합니다.

## 왜 필요한가

split_into_paragraphs는 줄바꿈을 문단 경계로 삼습니다. 원본 STT
전사본처럼 줄바꿈이 거의 없는 입력이 들어오면 회의록 전체가
"문단 하나"가 됩니다. 예전 코드는 max_chars를 넘는 문단을 그대로
청크 하나로 반환했으므로, 이 경우 청크 분할이 사실상 무력화되고
node.py가 다시 통짜 단일 호출과 같은 상태로 돌아갔습니다.

문장 경계(그리고 그마저 없으면 공백)로 강제 분할해 이 경우에도
청크가 여러 개 생기는지, 그리고 내용이 유실 없이 보존되는지
확인합니다.
"""

from meeting_analysis.chunking import CHUNK_MAX_CHARS, chunk_meeting_text


def _normalize(text: str) -> str:
    return "".join(text.split())


def test_줄바꿈이_없는_긴_원문도_여러_청크로_나뉜다():
    sentences = [f"그래서 {i}번째 주제에 대해 이야기했습니다." for i in range(300)]
    text = " ".join(sentences)
    assert len(text) > CHUNK_MAX_CHARS

    chunks = chunk_meeting_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_MAX_CHARS + 50 for chunk in chunks)
    assert _normalize("".join(chunks)) == _normalize(text)


def test_문장_부호도_없는_원문은_공백_단위로_나뉜다():
    text = " ".join(f"단어{i}" for i in range(2000))
    assert len(text) > CHUNK_MAX_CHARS

    chunks = chunk_meeting_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_MAX_CHARS + 20 for chunk in chunks)
    assert _normalize("".join(chunks)) == _normalize(text)


def test_짧은_문단들은_기존대로_줄바꿈_기준으로_묶인다():
    text = "\n\n".join(f"문단 {i} 내용입니다." for i in range(5))

    chunks = chunk_meeting_text(text)

    assert len(chunks) == 1
    assert chunks[0] == "\n\n".join(f"문단 {i} 내용입니다." for i in range(5))


def test_공백조차_없는_단일_토큰은_그대로_반환된다():
    text = "가" * (CHUNK_MAX_CHARS + 100)

    chunks = chunk_meeting_text(text)

    assert chunks == [text]
