import { useEffect, useState } from "react";
import { FileIcon, ArrowRightIcon } from "../icons";
import { getCompileCheckMode, setCompileCheckMode } from "../services/compileCheckModeStorage";
import { getSampleTemplates } from "../services/api";

export default function UploadForm({ onSubmit, disabled, disabledLabel = "Starting review…", showCompileCheckToggle = false, platformLabel = "Android" }) {
  const [sourceMode, setSourceMode] = useState("upload"); // upload | devops
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [defaultTemplate, setDefaultTemplate] = useState(null);
  const [useOwnTemplate, setUseOwnTemplate] = useState(false);
  const [devopsRepoUrl, setDevopsRepoUrl] = useState("");
  const [devopsPat, setDevopsPat] = useState("");
  const [devopsBranch, setDevopsBranch] = useState("");
  const [validationError, setValidationError] = useState("");
  const [compileCheckMode, setCompileCheckModeState] = useState(() => getCompileCheckMode());

  useEffect(() => {
    let cancelled = false;
    getSampleTemplates()
      .then((templates) => {
        if (cancelled) return;
        setDefaultTemplate(templates.find((template) => template.platform === platformLabel) || null);
      })
      .catch(() => { if (!cancelled) setDefaultTemplate(null); });
    return () => { cancelled = true; };
  }, [platformLabel]);

  const usingDefaultTemplate = !!defaultTemplate && !useOwnTemplate;

  function handleSubmit(event) {
    event.preventDefault();
    if (sourceMode === "upload") {
      if (!androidZip || !androidZip.name.endsWith(".zip")) {
        setValidationError("Android project must be a .zip file");
        return;
      }
    } else if (!devopsRepoUrl || !devopsPat) {
      setValidationError("Azure DevOps repo URL and PAT are both required");
      return;
    }
    if (!usingDefaultTemplate && (!excelTemplate || !excelTemplate.name.endsWith(".xlsx"))) {
      setValidationError("Review template must be a .xlsx file");
      return;
    }
    setValidationError("");
    onSubmit({
      androidZip: sourceMode === "upload" ? androidZip : null,
      excelTemplate: usingDefaultTemplate ? null : excelTemplate,
      devopsRepoUrl: sourceMode === "devops" ? devopsRepoUrl : null,
      devopsPat: sourceMode === "devops" ? devopsPat : null,
      devopsBranch: sourceMode === "devops" ? (devopsBranch || null) : null,
    });
  }

  function handleSelectMode(mode) {
    setCompileCheckMode(mode);
    setCompileCheckModeState(mode);
  }

  const canStart =
    (usingDefaultTemplate || !!excelTemplate) && (sourceMode === "upload" ? !!androidZip : !!devopsRepoUrl && !!devopsPat);

  return (
    <form onSubmit={handleSubmit} className="card elev-md" style={{ padding: 32 }}>
      <div className="card-kicker">Step 1 of 2</div>
      <div className="card-title" style={{ fontSize: 20 }}>Upload project files</div>
      <p className="card-body">Both a project source and a template are required to start a review.</p>

      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
        <button
          type="button"
          className={`btn ${sourceMode === "upload" ? "btn-primary" : ""}`}
          disabled={disabled}
          onClick={() => setSourceMode("upload")}
        >
          Upload files
        </button>
        <button
          type="button"
          className={`btn ${sourceMode === "devops" ? "btn-primary" : ""}`}
          disabled={disabled}
          onClick={() => setSourceMode("devops")}
        >
          Clone from Azure DevOps
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginTop: "var(--space-5)" }}>
        {sourceMode === "upload" ? (
          <div className="field">
            <label htmlFor="androidZip">{platformLabel} project (.zip)</label>
            <label className="dropzone">
              <FileIcon />
              {androidZip ? <span style={{ fontSize: 14 }}>{androidZip.name}</span> : <span style={{ fontSize: 14, color: "var(--color-text-faint)" }}>Choose ZIP file…</span>}
              <input
                id="androidZip"
                type="file"
                accept=".zip"
                disabled={disabled}
                onChange={(event) => setAndroidZip(event.target.files[0] ?? null)}
                style={{ display: "none" }}
              />
            </label>
          </div>
        ) : (
          <div className="field" style={{ gridColumn: "1 / -1", display: "grid", gap: "var(--space-3)" }}>
            <div>
              <label htmlFor="devopsRepoUrl">Repo URL</label>
              <input
                id="devopsRepoUrl"
                type="text"
                className="input"
                placeholder="https://dev.azure.com/org/project/_git/repo"
                disabled={disabled}
                value={devopsRepoUrl}
                onChange={(event) => setDevopsRepoUrl(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="devopsPat">Personal Access Token</label>
              <input
                id="devopsPat"
                type="password"
                className="input"
                disabled={disabled}
                value={devopsPat}
                onChange={(event) => setDevopsPat(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="devopsBranch">Branch (optional)</label>
              <input
                id="devopsBranch"
                type="text"
                className="input"
                placeholder="default branch"
                disabled={disabled}
                value={devopsBranch}
                onChange={(event) => setDevopsBranch(event.target.value)}
              />
            </div>
          </div>
        )}
        <div className="field">
          <label htmlFor="excelTemplate">Scoring template (.xlsx)</label>
          {usingDefaultTemplate ? (
            <div className="dropzone" style={{ justifyContent: "space-between" }}>
              <span style={{ fontSize: 14 }}>Using default: {defaultTemplate.filename}</span>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={disabled}
                onClick={() => setUseOwnTemplate(true)}
              >
                Choose a different file
              </button>
            </div>
          ) : (
            <>
              <label className="dropzone">
                <FileIcon />
                {excelTemplate ? <span style={{ fontSize: 14 }}>{excelTemplate.name}</span> : <span style={{ fontSize: 14, color: "var(--color-text-faint)" }}>Choose Excel file…</span>}
                <input
                  id="excelTemplate"
                  type="file"
                  accept=".xlsx"
                  disabled={disabled}
                  onChange={(event) => setExcelTemplate(event.target.files[0] ?? null)}
                  style={{ display: "none" }}
                />
              </label>
              {defaultTemplate && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ marginTop: 8 }}
                  disabled={disabled}
                  onClick={() => { setUseOwnTemplate(false); setExcelTemplate(null); }}
                >
                  Use default instead
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {showCompileCheckToggle && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <p className="card-body" style={{ marginBottom: "var(--space-2)" }}>Clause 1.4 evaluation</p>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              className={`btn ${compileCheckMode === "compiler" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("compiler")}
            >
              {platformLabel === "Android" || platformLabel === ".NET" ? "Compile-time lint (Docker)" : "Compile-time lint"}
            </button>
            {platformLabel === "Android" && (
              <button
                type="button"
                className={`btn ${compileCheckMode === "local" ? "btn-primary" : ""}`}
                disabled={disabled}
                onClick={() => handleSelectMode("local")}
              >
                Compile-time lint (local)
              </button>
            )}
            <button
              type="button"
              className={`btn ${compileCheckMode === "static" ? "btn-primary" : ""}`}
              disabled={disabled}
              onClick={() => handleSelectMode("static")}
            >
              Static file analysis
            </button>
          </div>
        </div>
      )}

      {validationError && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{validationError}</p>}

      <button
        type="submit"
        className="btn btn-primary btn-block"
        style={{ marginTop: "var(--space-5)" }}
        disabled={disabled || !canStart}
      >
        {disabled ? disabledLabel : "Start review"}
        <ArrowRightIcon />
      </button>
    </form>
  );
}
