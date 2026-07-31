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
    # Guard against non-string types (e.g., float, int)
    if not isinstance(version_str, str):
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
    if compile_sdk is not None and isinstance(compile_sdk, int) and compile_sdk < LATEST_VERSIONS["compile_sdk"]:
        warnings.append(
            {"issue": f"compileSdkVersion {compile_sdk} is outdated, latest is {LATEST_VERSIONS['compile_sdk']}"}
        )

    target_sdk = gradle_info.get("target_sdk")
    if target_sdk is not None and isinstance(target_sdk, int) and target_sdk < LATEST_VERSIONS["target_sdk"]:
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


IOS_LATEST_VERSIONS = {
    "deployment_target": (17, 0),
    "swift_version": (5, 9),
}


def compare_ios_versions(build_info: dict) -> list:
    warnings = []

    deployment_target = _parse_version_tuple(build_info.get("deployment_target"))
    if deployment_target is not None and deployment_target < IOS_LATEST_VERSIONS["deployment_target"]:
        warnings.append(
            {"issue": f"iOS deployment target {build_info.get('deployment_target')} is outdated, latest is 17.0+"}
        )

    swift_version = _parse_version_tuple(build_info.get("swift_version"))
    if swift_version is not None and swift_version < IOS_LATEST_VERSIONS["swift_version"]:
        warnings.append(
            {"issue": f"Swift version {build_info.get('swift_version')} is outdated, latest is 5.9+"}
        )

    return warnings


DOTNET_LATEST_VERSIONS = {
    "target_framework": (8, 0),
}


def compare_dotnet_versions(build_info: dict) -> list:
    warnings = []

    target_framework = _parse_version_tuple(build_info.get("target_framework"))
    if target_framework is not None and target_framework < DOTNET_LATEST_VERSIONS["target_framework"]:
        warnings.append(
            {"issue": f"Target framework {build_info.get('target_framework')} is outdated, latest is net8.0+"}
        )

    return warnings
