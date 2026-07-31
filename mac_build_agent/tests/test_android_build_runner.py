from app.android_build_runner import _resolve_sdk_dir, find_app_module_path, find_gradle_root


def test_find_gradle_root_locates_a_nested_settings_gradle_kts(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "settings.gradle.kts").write_text("")
    (project_root / "gradlew").write_text("#!/bin/sh")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_locates_a_nested_settings_gradle(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "settings.gradle").write_text("")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_falls_back_to_build_gradle_when_no_settings_file(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "build.gradle").write_text("")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_falls_back_to_the_extraction_root_when_nothing_found(tmp_path):
    assert find_gradle_root(tmp_path) == tmp_path


def test_find_app_module_path_via_groovy_apply_plugin_syntax(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("apply plugin: 'com.android.application'\n")

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_via_kotlin_dsl_plugins_block(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle.kts").write_text('plugins {\n    id("com.android.application")\n}\n')

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_skips_library_modules(tmp_path):
    lib_dir = tmp_path / "countrycodepicker"
    lib_dir.mkdir()
    (lib_dir / "build.gradle").write_text("apply plugin: 'com.android.library'\n")

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("apply plugin: 'com.android.application'\n")

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_resolves_a_version_catalog_alias(tmp_path):
    catalog_dir = tmp_path / "gradle"
    catalog_dir.mkdir()
    (catalog_dir / "libs.versions.toml").write_text(
        '[plugins]\n'
        'android-application = { id = "com.android.application", version.ref = "agp" }\n'
    )
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle.kts").write_text(
        'plugins {\n    alias(libs.plugins.android.application)\n}\n'
    )

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_returns_none_when_no_application_module_found(tmp_path):
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    (lib_dir / "build.gradle").write_text("apply plugin: 'com.android.library'\n")

    assert find_app_module_path(tmp_path) is None


def test_resolve_sdk_dir_prefers_android_home(monkeypatch):
    monkeypatch.setenv("ANDROID_HOME", "/custom/android-home")
    monkeypatch.setenv("ANDROID_SDK_ROOT", "/custom/android-sdk-root")
    assert _resolve_sdk_dir() == "/custom/android-home"


def test_resolve_sdk_dir_falls_back_to_android_sdk_root(monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.setenv("ANDROID_SDK_ROOT", "/custom/android-sdk-root")
    assert _resolve_sdk_dir() == "/custom/android-sdk-root"


def test_resolve_sdk_dir_falls_back_to_the_conventional_mac_location(monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    assert _resolve_sdk_dir().endswith("Library/Android/sdk")
