import { redirect } from "next/navigation";

// Legacy route — the real project detail page lives at /projects/[id].
// Kept as a redirect so old links (bookmarks, external references) don't 404.
export default async function LegacyProjectDetailRedirect(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  redirect(`/projects/${params.id}`);
}
