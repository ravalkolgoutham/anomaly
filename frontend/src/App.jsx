import { useState } from "react";
import "./App.css";

const SAMPLE_CODE = `// Contract: return -1 if items is null, count is negative,
// or index is outside [0, count).
int get_item(int *items, int count, int index) {
    if (index <= count) {
        return items[index];
    }
    return -1;
}
`;

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = Array.isArray(data.detail)
      ? JSON.stringify(data.detail)
      : data.detail || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return data;
}

function App() {
  const [sourceCode, setSourceCode] = useState(SAMPLE_CODE);
  const [repairedCode, setRepairedCode] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [validation, setValidation] = useState(null);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function analyzeCode() {
    setBusy(true);
    setError("");
    setAnalysis(null);
    setValidation(null);
    setRepairedCode("");
    setReviewed(false);

    try {
      const result = await postJson("http://127.0.0.1:8000/analyze", {
        source_code: sourceCode,
      });

      setAnalysis(result);
      setRepairedCode(result.repaired_code || "");
    } catch (err) {
      setError(`Analysis failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function validateCode() {
    if (!reviewed || !repairedCode.trim()) return;

    setBusy(true);
    setError("");
    setValidation(null);

    try {
      const result = await postJson("http://127.0.0.1:8000/validate", {
        cpp_code: repairedCode,
      });

      setValidation(result);
    } catch (err) {
      setError(`Sandbox validation failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  const score = analysis?.defect_probability_score;
  const result = validation?.validation_results;

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">CODEXGLUE · LOCAL ANALYSIS</p>
          <h1>AI Code Repair</h1>
          <p className="subtitle">
            Analyze C/C++ code, review a proposed repair, then validate it in Docker.
          </p>
        </div>
        <span className="model-badge">Qwen 2.5 Coder · Local</span>
      </header>

      <section className="notice">
        <strong>Experimental model</strong>
        <span>
          Test accuracy 56.59% · ROC-AUC 56.06%. Review every repair suggestion.
        </span>
      </section>

      <section className="card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">STEP 1</p>
            <h2>Source code</h2>
          </div>
          <button className="primary-button" onClick={analyzeCode} disabled={busy}>
            {busy ? "Analyzing…" : "Analyze code"}
          </button>
        </div>

        <textarea
          className="code-box source-box"
          aria-label="Source code"
          spellCheck="false"
          value={sourceCode}
          onChange={(event) => setSourceCode(event.target.value)}
        />
      </section>

      {error && <div className="error-box">{error}</div>}

      {analysis && (
        <section className="summary-grid">
          <article className="card metric-card">
            <p className="eyebrow">DEFECT PROBABILITY</p>
            <strong className="score">
              {typeof score === "number" ? `${(score * 100).toFixed(2)}%` : "—"}
            </strong>
            <span className={analysis.is_defective ? "flagged" : "below-threshold"}>
              {analysis.is_defective ? "Flagged for review" : "Below threshold"}
            </span>
          </article>

          <article className="card">
            <p className="eyebrow">ANALYSIS</p>
            {analysis.localization_data ? (
              <>
                <p>
                  <strong>Function:</strong>{" "}
                  {analysis.localization_data.suspicious_function}
                </p>
                <p>
                  <strong>Line:</strong>{" "}
                  {analysis.localization_data.suspicious_line_number}
                </p>
                <p>{analysis.localization_data.defect_explanation}</p>
              </>
            ) : (
              <p>No repair was returned. The score may be below the model threshold.</p>
            )}
          </article>
        </section>
      )}

      {analysis?.repaired_code && (
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">STEP 2</p>
              <h2>Review and edit the proposed repair</h2>
            </div>
            <span className="subtitle">The repaired-code panel is editable.</span>
          </div>

          <div className="code-columns">
            <label>
              <span className="panel-title">Original</span>
              <textarea
                className="code-box"
                value={sourceCode}
                readOnly
                spellCheck="false"
                aria-label="Original code"
              />
            </label>

            <label>
              <span className="panel-title">Proposed repair</span>
              <textarea
                className="code-box"
                value={repairedCode}
                spellCheck="false"
                aria-label="Proposed repaired code"
                onChange={(event) => {
                  setRepairedCode(event.target.value);
                  setReviewed(false);
                  setValidation(null);
                }}
              />
            </label>
          </div>

          <label className="review-check">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(event) => setReviewed(event.target.checked)}
            />
            I reviewed the proposed C++ and want to run this exact version in Docker.
          </label>

          <button
            className="validate-button"
            onClick={validateCode}
            disabled={busy || !reviewed || !repairedCode.trim()}
          >
            {busy ? "Validating…" : "Validate reviewed code"}
          </button>
        </section>
      )}

      {validation && result && (
        <section className={`card validation-card ${validation.regression_failed ? "failed" : "passed"}`}>
          <p className="eyebrow">STEP 3 · DOCKER SANDBOX</p>
          <h2>{result.status === "success" ? "Assertions passed" : "Validation did not pass"}</h2>
          <p><strong>Status:</strong> {result.status}</p>
          <pre>{result.stdout || "No standard output."}</pre>
          {result.stderr && <pre className="stderr">{result.stderr}</pre>}
        </section>
      )}

      <footer>
        A passing result means the included assertions passed; it does not prove
        correctness for every possible input.
      </footer>
    </main>
  );
}

export default App;