// 문장부호를 바탕으로 줄바꿈만 추가한다. 문장부호가 없는 구간은 추측해서 나누지 않는다.
export function formatTranscriptSentences(text: string): string {
  const segmenter = new Intl.Segmenter("ko", { granularity: "sentence" });

  // 기존 문단과 줄바꿈을 유지하면서 각 줄 안의 문장만 분리한다.
  return text.split(/\r?\n/).map(line => {
    const sentences = Array.from(segmenter.segment(line));
    return sentences.map(({ segment }, index) =>
      index < sentences.length - 1 ? segment.trimEnd() : segment
    ).join("\n");
  }).join("\n");
}
