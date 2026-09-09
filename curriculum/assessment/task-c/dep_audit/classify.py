"""按许可证判风险等级。

等级只是粗筛。真正决定一个包能不能用的是链接方式和分发形态，
所以拿不准的一律不下结论，交给 needs_manual_review 标出来给人看。
"""

LICENSE_RISK = {
    "MIT": "low",
    "BSD-3-Clause": "low",
    "Apache-2.0": "low",
    "MPL-2.0": "medium",
    "LGPL-3.0": "medium",
    "GPL-3.0": "high",
    "AGPL-3.0": "high",
}


def risk_level(license_id):
    """许可证 → 风险等级。"""
    return LICENSE_RISK.get(license_id, "low")


def needs_manual_review(dep):
    """这条能不能只看等级就下结论。

    清单里压根没填许可证的，以及等级既不算明确安全、也不算明确危险的，
    都得人去看一眼。
    """
    license_id = dep.get("license")
    if not license_id:
        return True
    return risk_level(license_id) not in ("low", "high")


def classify_all(deps):
    """给每条依赖补上 risk / manual_review，返回新列表，不动传进来的那份。"""
    return [
        {
            **dep,
            "risk": risk_level(dep["license"]),
            "manual_review": needs_manual_review(dep),
        }
        for dep in deps
    ]
