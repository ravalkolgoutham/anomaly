from pathlib import Path
import subprocess
import tempfile

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.sandbox import execute_cpp_validation
from backend.llm_pipeline import analyze_and_repair_code


app = FastAPI(title="AI Code Repair API")

# Vite may use 5174 when 5173 is already occupied.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "xgboost_defect_model.pkl"

try:
    model = joblib.load(MODEL_PATH)
except Exception as exc:
    model = None
    print(f"Could not load model at {MODEL_PATH}: {exc}")


class AnalyzeRequest(BaseModel):
    source_code: str


class ValidateRequest(BaseModel):
    cpp_code: str


def extract_cpp_features(source_code: str) -> list[int]:
    """Return the AST feature counts used by the trained model."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_cpp

        language = Language(tree_sitter_cpp.language())
        parser = Parser(language)
        tree = parser.parse(source_code.encode("utf-8"))

        counts = {
            "num_lines": len(source_code.splitlines()),
            "num_ifs": 0,
            "num_loops": 0,
            "num_functions": 0,
            "num_try_catch": 0,
        }

        def visit(node):
            node_type = node.type
            if node_type == "if_statement":
                counts["num_ifs"] += 1
            elif node_type in ("for_statement", "while_statement", "do_statement"):
                counts["num_loops"] += 1
            elif node_type == "function_definition":
                counts["num_functions"] += 1
            elif node_type in ("try_statement", "catch_clause"):
                counts["num_try_catch"] += 1

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return [
            counts["num_lines"],
            counts["num_ifs"],
            counts["num_loops"],
            counts["num_functions"],
            counts["num_try_catch"],
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not extract C++ features: {exc}",
        ) from exc


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    if not request.source_code.strip():
        raise HTTPException(status_code=422, detail="source_code cannot be empty")
    if model is None:
        raise HTTPException(status_code=500, detail="The XGBoost model did not load")

    features = extract_cpp_features(request.source_code)

    try:
        probability = float(model.predict_proba(np.array([features]))[0][1])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {exc}") from exc

    result = {
        "defect_probability_score": probability,
        "is_defective": probability >= 0.5,
        "localization_data": None,
        "repaired_code": None,
        "generated_tests": None,
        "validation_required": True,
    }

    if probability >= 0.5:
        try:
            repair = analyze_and_repair_code(request.source_code)
            result["localization_data"] = {
                "suspicious_function": repair.get("suspicious_function"),
                "suspicious_line_number": repair.get("suspicious_line_number"),
                "defect_explanation": repair.get("defect_explanation"),
            }
            result["repaired_code"] = repair.get("corrected_code")
            result["generated_tests"] = repair.get("generated_tests")
        except Exception as exc:
            result["repair_error"] = str(exc)

    return result


@app.post("/validate")
def validate(request: ValidateRequest):
    if not request.cpp_code.strip():
        raise HTTPException(status_code=422, detail="cpp_code cannot be empty")

    result = execute_cpp_validation(request.cpp_code)
    return {
        "validation_results": result,
        "regression_failed": result.get("status") != "success",
    }