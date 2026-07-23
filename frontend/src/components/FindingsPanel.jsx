export default function FindingsPanel({ warnings, testCoverage, secretsFound }) {
  const hasWarnings = warnings && warnings.length > 0;
  const hasSecrets = secretsFound && secretsFound.length > 0;
  const hasCoverage = testCoverage !== null && testCoverage !== undefined;

  if (!hasWarnings && !hasSecrets && !hasCoverage) {
    return null;
  }

  return (
    <div className="border rounded p-4 space-y-3 bg-gray-50">
      <h3 className="font-medium">Findings</h3>
      {hasCoverage && (
        <p className="text-sm">
          Test coverage: <span className="font-semibold">{testCoverage}%</span>
        </p>
      )}
      {hasWarnings && (
        <div>
          <p className="text-sm font-medium text-yellow-700">Warnings</p>
          <ul className="list-disc list-inside text-sm text-yellow-700">
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {hasSecrets && (
        <div>
          <p className="text-sm font-medium text-red-700">Potential secrets found</p>
          <ul className="list-disc list-inside text-sm text-red-700">
            {secretsFound.map((secret, index) => (
              <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
