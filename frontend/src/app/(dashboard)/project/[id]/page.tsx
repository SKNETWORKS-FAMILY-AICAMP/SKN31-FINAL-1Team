import { redirect } from "next/navigation";

// 예전 경로 — 실제 프로젝트 상세 화면은 /projects/[id]에 있다.
// 기존 링크(북마크, 외부 참조)가 404 나지 않도록 리다이렉트만 남겨둔다.
export default async function LegacyProjectDetailRedirect(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  redirect(`/projects/${params.id}`);
}
