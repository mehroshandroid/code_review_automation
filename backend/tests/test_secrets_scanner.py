from pathlib import Path

from app.analyzer.secrets_scanner import scan_directory


def test_finds_hardcoded_api_key(tmp_path: Path):
    java_file = tmp_path / "Constants.java"
    java_file.write_text(
        'public class Constants {\n'
        '    public static final String API_KEY = "ab12cd34ef56gh78ij90kl12mn34op56";\n'
        '}\n'
    )
    findings = scan_directory(tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == str(java_file)
    assert findings[0]["line"] == 2
    assert findings[0]["pattern"] == "api_key"


def test_finds_firebase_key(tmp_path: Path):
    xml_file = tmp_path / "google-services.json.xml"
    xml_file.write_text('"key": "AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY"\n')
    findings = scan_directory(tmp_path)
    assert any(f["pattern"] == "firebase_key" for f in findings)


def test_no_findings_in_clean_code(tmp_path: Path):
    java_file = tmp_path / "MainActivity.java"
    java_file.write_text('public class MainActivity {\n    void onCreate() {}\n}\n')
    assert scan_directory(tmp_path) == []


def test_ignores_non_source_extensions(tmp_path: Path):
    binary_like = tmp_path / "notes.txt"
    binary_like.write_text('api_key = "ab12cd34ef56gh78ij90kl12mn34op56"\n')
    assert scan_directory(tmp_path) == []
