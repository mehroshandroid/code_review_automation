from typing import Optional

LATEST_VERSIONS = {
    "compile_sdk": 34,
    "target_sdk": 34,
    "gradle": (8, 0),
    "kotlin": (1, 9),
}


def _parse_version_tuple(version_str: Optional[str]):
    if not version_str:
        return None
    nums = []
    for part in version_str.split("."):
        digits = "".join(c for c in part if c.isdigit())
        if digits == "":
            break
        nums.append(int(digits))
    return tuple(nums) if nums else None


def compare_versions(gradle_info: dict) -> list:
    warnings = []

    compile_sdk = gradle_info.get("compile_sdk")
    if compile_sdk is not None and compile_sdk < LATEST_VERSIONS["compile_sdk"]:
        warnings.append(
            {"issue": f"compileSdkVersion {compile_sdk} is outdated, latest is {LATEST_VERSIONS['compile_sdk']}"}
        )

    target_sdk = gradle_info.get("target_sdk")
    if target_sdk is not None and target_sdk < LATEST_VERSIONS["target_sdk"]:
        warnings.append(
            {"issue": f"targetSdkVersion {target_sdk} is outdated, latest is {LATEST_VERSIONS['target_sdk']}"}
        )

    gradle_version = _parse_version_tuple(gradle_info.get("gradle_version"))
    if gradle_version is not None and gradle_version < LATEST_VERSIONS["gradle"]:
        warnings.append(
            {"issue": f"Gradle version {gradle_info.get('gradle_version')} is outdated, latest is 8.0+"}
        )

    kotlin_version = _parse_version_tuple(gradle_info.get("kotlin_version"))
    if kotlin_version is not None and kotlin_version < LATEST_VERSIONS["kotlin"]:
        warnings.append(
            {"issue": f"Kotlin version {gradle_info.get('kotlin_version')} is outdated, latest is 1.9+"}
        )

    return warnings
