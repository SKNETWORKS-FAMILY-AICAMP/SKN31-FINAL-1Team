import { describe, expect, it } from "vitest";
import { htmlToPlainText, stripPmReviewNotes } from "./htmlToPlainText";

describe("stripPmReviewNotes", () => {
  it("removes a trailing PM 확인 사항 block", () => {
    const html =
      "<p>React와 Node.js를 사용한다.</p><p><strong>PM 확인 사항</strong></p><ul><li>인증 방식을 확정해 주세요.</li></ul>";
    expect(stripPmReviewNotes(html)).toBe("<p>React와 Node.js를 사용한다.</p>");
  });

  it("leaves content without a PM 확인 사항 block untouched", () => {
    const html = "<p>React와 Node.js를 사용한다.</p>";
    expect(stripPmReviewNotes(html)).toBe(html);
  });

  it("returns empty input as-is", () => {
    expect(stripPmReviewNotes("")).toBe("");
  });
});

describe("htmlToPlainText + stripPmReviewNotes (PPTX export path)", () => {
  it("keeps PM 확인 사항 out of the plain text used for slides", () => {
    const html =
      "<p>React와 Node.js를 사용한다.</p><p><strong>PM 확인 사항</strong></p><ul><li>인증 방식을 확정해 주세요.</li></ul>";
    const text = htmlToPlainText(stripPmReviewNotes(html));
    expect(text).toBe("React와 Node.js를 사용한다.");
    expect(text).not.toContain("PM 확인 사항");
    expect(text).not.toContain("인증 방식을 확정해 주세요.");
  });
});
