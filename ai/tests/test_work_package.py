"""
tests/test_work_package.py

2026-09-11 (Phase 2 item 7): WorkPackage 그룹화 + 그룹 기반 정렬/응집도.
전부 순수 계산이라 결정적으로 확인한다.
"""

import pytest

from assignee_recommend.rule_filter import schedule_assignments, sort_units_by_priority
from work_package import (
    apply_split_decisions,
    assemble_packages,
    assert_full_coverage,
    build_work_packages,
)


def _unit(uid, req, hours=4.0, feature=None, skills=None, deps=None):
    return {
        "unit_id": uid,
        "parent_task_id": None,
        "title": uid,
        "description": "d",
        "required_skills": skills if skills is not None else ["Django"],
        "estimated_hours": hours,
        "source_req_id": req,
        "depends_on": deps or [],
        "risk_buffer_factor": None,
        "feature_area": feature,
    }


# ---------------------------------------------------------------------------
# build_work_packages
# ---------------------------------------------------------------------------
def test_same_feature_area_groups_across_requirements():
    units = [
        _unit("A", "FR-01", feature="주문"),
        _unit("B", "FR-02", feature="주문"),
        _unit("C", "FR-03", feature="결제"),
    ]
    out = build_work_packages(units)
    assert out["package_by_unit"]["A"] == out["package_by_unit"]["B"]
    assert out["package_by_unit"]["C"] != out["package_by_unit"]["A"]
    order_pkg = next(p for p in out["packages"] if p["package_id"] == out["package_by_unit"]["A"])
    assert sorted(order_pkg["source_req_ids"]) == ["FR-01", "FR-02"]
    assert order_pkg["estimated_hours"] == 8.0


def test_no_feature_area_falls_back_to_requirement():
    units = [_unit("A", "FR-01"), _unit("B", "FR-01"), _unit("C", "FR-02")]
    out = build_work_packages(units)
    assert out["package_by_unit"]["A"] == out["package_by_unit"]["B"]
    assert out["package_by_unit"]["C"] != out["package_by_unit"]["A"]


def test_dependency_package_ids_from_cross_package_unit_deps():
    units = [
        _unit("DESIGN", "FR-01", feature="주문"),
        _unit("TEST", "FR-02", feature="테스트", deps=["DESIGN"]),
    ]
    out = build_work_packages(units)
    test_pkg = next(p for p in out["packages"] if "TEST" in p["unit_ids"])
    design_pid = out["package_by_unit"]["DESIGN"]
    assert test_pkg["dependency_package_ids"] == [design_pid]


def test_merged_required_skills_dedup_and_order():
    units = [
        _unit("A", "FR-01", feature="주문", skills=["Django", "REST API"]),
        _unit("B", "FR-01", feature="주문", skills=["REST API", "MySQL"]),
    ]
    pkg = build_work_packages(units)["packages"][0]
    assert pkg["required_skills"] == ["Django", "REST API", "MySQL"]


# ---------------------------------------------------------------------------
# assert_full_coverage
# ---------------------------------------------------------------------------
def test_full_coverage_passes_for_build_output():
    units = [_unit("A", "FR-01", feature="주문"), _unit("B", "FR-02")]
    out = build_work_packages(units)
    assert_full_coverage(out["package_by_unit"], units)  # 예외 없음


def test_full_coverage_raises_on_missing_unit():
    units = [_unit("A", "FR-01"), _unit("B", "FR-02")]
    with pytest.raises(ValueError):
        assert_full_coverage({"A": "WP-001"}, units)  # B 누락


# ---------------------------------------------------------------------------
# sort_units_by_priority: package 클러스터링
# ---------------------------------------------------------------------------
def _with_packages(units):
    pbu = build_work_packages(units)["package_by_unit"]
    for u in units:
        u["package_id"] = pbu[u["unit_id"]]
    return units


def test_sort_keeps_package_mates_adjacent():
    # 같은 feature "주문"이 FR-01, FR-03에 흩어져 있지만 정렬 후엔 인접해야 한다
    units = _with_packages([
        _unit("O1", "FR-01", feature="주문"),
        _unit("P1", "FR-02", feature="결제"),
        _unit("O2", "FR-03", feature="주문"),
    ])
    prio = {"FR-01": "High", "FR-02": "High", "FR-03": "High"}
    ordered = [u["unit_id"] for u in sort_units_by_priority(units, prio)]
    assert abs(ordered.index("O1") - ordered.index("O2")) == 1


def test_sort_without_package_id_matches_requirement_clustering():
    units = [
        _unit("A", "FR-01", hours=2), _unit("B", "FR-02", hours=9), _unit("C", "FR-01", hours=2),
    ]
    prio = {"FR-01": "High", "FR-02": "High"}
    ordered = [u["unit_id"] for u in sort_units_by_priority(units, prio)]
    # FR-02(9h) 클러스터가 FR-01(4h)보다 앞, FR-01끼리는 생성 순서 유지
    assert ordered == ["B", "A", "C"]


# ---------------------------------------------------------------------------
# schedule_assignments: package 응집도로 한 기능을 한 사람이
# ---------------------------------------------------------------------------
def test_feature_spanning_requirements_goes_to_one_assignee():
    units = _with_packages([
        _unit("O1", "FR-01", feature="주문", hours=6),
        _unit("O2", "FR-02", feature="주문", hours=6),
    ])
    units = sort_units_by_priority(units, {"FR-01": "High", "FR-02": "High"})
    members = [
        {"employee_id": "1", "skills": ["Django"], "past_similar_tasks": [], "certifications": []},
        {"employee_id": "2", "skills": ["Django"], "past_similar_tasks": [], "certifications": []},
    ]
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100)
    assignees = {r["unit"]["unit_id"]: r["employee_id"] for r in result}
    assert assignees["O1"] == assignees["O2"]  # 같은 기능 -> 같은 담당자


# ---------------------------------------------------------------------------
# apply_split_decisions (Phase 3 item 10-11)
# ---------------------------------------------------------------------------
def test_split_uses_valid_llm_unit_groups():
    units = _with_packages([
        _unit("UI1", "FR-01", feature="결제", skills=["React"]),
        _unit("API1", "FR-01", feature="결제", skills=["Django"]),
    ])
    pbu = {u["unit_id"]: u["package_id"] for u in units}
    pid = pbu["UI1"]
    new_map = apply_split_decisions(units, pbu, {pid: {"reason": "역할 분리", "unit_groups": [["UI1"], ["API1"]]}})
    assert new_map["UI1"] != new_map["API1"]
    assert new_map["UI1"].startswith(pid + "-")
    assert_full_coverage(new_map, units)


def test_invalid_groups_fall_back_to_auto_split_by_role():
    units = _with_packages([
        _unit("UI1", "FR-01", feature="결제", skills=["React"]),
        _unit("API1", "FR-01", feature="결제", skills=["Django"]),
    ])
    pbu = {u["unit_id"]: u["package_id"] for u in units}
    pid = pbu["UI1"]
    # unit_groups가 API1을 빠뜨림 -> partition 아님 -> 코드 자동 분할(역할별)
    new_map = apply_split_decisions(units, pbu, {pid: {"reason": "x", "unit_groups": [["UI1"]]}})
    assert new_map["UI1"] != new_map["API1"]


def test_auto_split_by_requirement_when_spanning_reqs():
    units = _with_packages([
        _unit("A", "FR-01", feature="주문", skills=["Django"]),
        _unit("B", "FR-02", feature="주문", skills=["Django"]),
    ])
    pbu = {u["unit_id"]: u["package_id"] for u in units}
    pid = pbu["A"]
    new_map = apply_split_decisions(units, pbu, {pid: {"reason": "분량", "unit_groups": []}})
    assert new_map["A"] != new_map["B"]  # 요구사항별로 갈림


def test_unsplittable_package_left_unchanged():
    units = _with_packages([
        _unit("A", "FR-01", feature="주문", skills=["Django"]),
        _unit("B", "FR-01", feature="주문", skills=["Django"]),
    ])
    pbu = {u["unit_id"]: u["package_id"] for u in units}
    pid = pbu["A"]
    new_map = apply_split_decisions(units, pbu, {pid: {"reason": "?", "unit_groups": []}})
    assert new_map == pbu  # 요구사항도 역할도 1개뿐 -> 분할 취소


def test_assemble_packages_reflects_split():
    units = _with_packages([
        _unit("UI1", "FR-01", feature="결제", skills=["React"]),
        _unit("API1", "FR-01", feature="결제", skills=["Django"]),
    ])
    pbu = {u["unit_id"]: u["package_id"] for u in units}
    pid = pbu["UI1"]
    new_map = apply_split_decisions(units, pbu, {pid: {"reason": "r", "unit_groups": [["UI1"], ["API1"]]}})
    packages = assemble_packages(units, new_map)
    assert len(packages) == 2
    assert {p["package_id"] for p in packages} == set(new_map.values())
