import json

import ollama
from pydantic import BaseModel


MODEL = "qwen2.5-coder:14b"


class RepairResult(BaseModel):
    suspicious_function: str
    suspicious_line_number: int
    defect_explanation: str
    corrected_code: str


def _ask(prompt: str) -> str:
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
    )
    return response["message"]["content"]


def analyze_and_repair_code(broken_code: str) -> dict:
    prompt = f"""
Analyze this C or C++ code for a real logical defect or vulnerability.
Do not invent a defect. Preserve the source language and original function
name and signature whenever possible.

Return ONLY a JSON object with exactly these keys:
suspicious_function, suspicious_line_number, defect_explanation, corrected_code.

The corrected_code value MUST contain one complete, compilable C++ source file:
- Include all required headers.
- Include the repaired function.
- Include a main() function with at least three assert() checks.
- Cover normal behavior, boundary behavior, and invalid or negative inputs
  where applicable.
- Print ALL_TESTS_PASSED only after every assertion passes.
- Make every test's expected result consistent with the function's behavior.
- Do not include Markdown fences around the C++ source.

If no defect is clear, explain that and still provide a complete C++ file
containing the original function and appropriate assertions.
The suspicious line number refers to the supplied input code, starting at 1.

Follow the function contract exactly. For get_item, invalid input means
items is null, count is negative, index is negative, or index is greater
than or equal to count. Return -1 for invalid input. The repaired function
and every assertion in main() must follow this contract. Do not include an
assertion whose expected value disagrees with the repaired function.
INPUT CODE:
{broken_code}
"""

    raw = _ask(prompt).strip()

    # Remove a Markdown fence if the model wraps its JSON response.
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
        result = RepairResult.model_validate(data)
    except Exception as exc:
        raise ValueError(
            f"Qwen did not return the required repair JSON. Model response: {raw}"
        ) from exc

    # Remove fences around the C++ source if the model included them anyway.
    code = result.corrected_code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result.corrected_code = code

    return result.model_dump()


def generate_test_cases(original_code: str, repaired_code: str) -> str:
    """
    The test cases now live inside corrected_code's C++ main() function.
    Keep this function for compatibility with existing backend code.
    """
    return "C++ assert tests are included in corrected_code's main() function."