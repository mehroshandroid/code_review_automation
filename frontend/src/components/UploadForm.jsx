import { useState } from "react";

export default function UploadForm({ onSubmit, disabled }) {
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [validationError, setValidationError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!androidZip || !androidZip.name.endsWith(".zip")) {
      setValidationError("Android project must be a .zip file");
      return;
    }
    if (!excelTemplate || !excelTemplate.name.endsWith(".xlsx")) {
      setValidationError("Review template must be a .xlsx file");
      return;
    }
    setValidationError("");
    onSubmit(androidZip, excelTemplate);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700" htmlFor="androidZip">
          Android Project (.zip)
        </label>
        <input
          id="androidZip"
          type="file"
          accept=".zip"
          disabled={disabled}
          onChange={(event) => setAndroidZip(event.target.files[0] ?? null)}
          className="mt-1 block w-full"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700" htmlFor="excelTemplate">
          Review Template (.xlsx)
        </label>
        <input
          id="excelTemplate"
          type="file"
          accept=".xlsx"
          disabled={disabled}
          onChange={(event) => setExcelTemplate(event.target.files[0] ?? null)}
          className="mt-1 block w-full"
        />
      </div>
      {validationError && <p className="text-red-600 text-sm">{validationError}</p>}
      <button
        type="submit"
        disabled={disabled}
        className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
      >
        {disabled ? "Uploading..." : "Start Review"}
      </button>
    </form>
  );
}
