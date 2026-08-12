export function fmtTime(iso) {
    if (!iso)
        return "-";
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
export function statusLabel(status) {
    const map = {
        pending: "대기(미배정)",
        waiting_approval: "승인 대기",
        assigned: "배정됨",
        active: "진행중",
        done: "완료",
        delayed: "지연",
    };
    return map[status] ?? status;
}
export function statusClass(status) {
    return `status status--${status}`;
}
export function escapeHtml(s) {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
