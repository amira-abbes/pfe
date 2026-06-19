import argparse
import contextlib
import io
import json
import os
import traceback
from pathlib import Path


def _cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def _strip_non_python_lines(source: str) -> str:
    lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%") or stripped.startswith("!"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute notebook Python code cells without a Jupyter CLI dependency.")
    parser.add_argument("--input", required=True, help="Notebook to execute.")
    parser.add_argument("--output", required=True, help="Executed notebook output path.")
    parser.add_argument("--timeout", type=int, default=2400, help="Accepted for service compatibility.")
    parser.add_argument("--kernel", default="python3", help="Accepted for service compatibility.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLBACKEND", "Agg")

    notebook = json.loads(input_path.read_text(encoding="utf-8"))
    def display(*values) -> None:
        for value in values:
            print(value)

    namespace = {
        "__name__": "__main__",
        "__file__": str(input_path),
        "display": display,
    }

    executed_count = 0
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        source = _strip_non_python_lines(_cell_source(cell))
        if not source.strip():
            continue

        executed_count += 1
        cell["execution_count"] = executed_count
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                exec(compile(source, f"{input_path.name}:cell_{index}", "exec"), namespace)
        except Exception as exc:
            error_text = traceback.format_exc()
            cell["outputs"] = [
                {
                    "output_type": "error",
                    "ename": exc.__class__.__name__,
                    "evalue": str(exc),
                    "traceback": error_text.splitlines(),
                }
            ]
            output_path.write_text(json.dumps(notebook, ensure_ascii=False), encoding="utf-8")
            print(stdout.getvalue(), end="")
            raise

        text = stdout.getvalue()
        cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": text}] if text else []
        print(text, end="")

    output_path.write_text(json.dumps(notebook, ensure_ascii=False), encoding="utf-8")
    print(f"Notebook execute : {output_path}")


if __name__ == "__main__":
    main()
