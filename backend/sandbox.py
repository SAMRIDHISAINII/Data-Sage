import ast
import builtins
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import duckdb
import numpy as np
import pandas as pd

MAX_ROWS = 500
EXEC_TIMEOUT = 30


class GuardrailError(Exception):
    pass


FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|install|load|pragma|call|"
    r"vacuum|checkpoint|truncate|grant|read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|glob|getenv)\b",
    re.I,
)


def validate_sql(sql: str) -> str:
    s = re.sub(r"--.*?$", "", sql, flags=re.M)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S).strip().rstrip(";").strip()
    if not s:
        raise GuardrailError("Empty SQL statement")
    if ";" in s:
        raise GuardrailError("Only a single SQL statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise GuardrailError("Only SELECT / WITH queries are allowed")
    m = FORBIDDEN_SQL.search(s)
    if m:
        raise GuardrailError(f"Forbidden SQL keyword: {m.group(0).upper()}")
    return s


def run_sql(df: pd.DataFrame, sql: str) -> pd.DataFrame:
    sql = validate_sql(sql)
    con = duckdb.connect(database=":memory:")
    try:
        con.register("data", df)
        wrapped = f"SELECT * FROM ({sql}) AS __q LIMIT {MAX_ROWS + 1}"
        return _with_timeout(lambda: con.execute(wrapped).df())
    finally:
        con.close()


BANNED_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "globals", "locals", "getattr", "setattr", "delattr",
    "input", "breakpoint", "exit", "quit", "vars", "dir", "help", "memoryview", "type", "super", "object",
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins", "pickle", "requests",
}
BANNED_ATTRS = {"eval", "system", "popen", "spawn", "fork", "exec", "load", "loads", "dump", "dumps"}
SAFE_BUILTINS = [
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max", "min", "range",
    "round", "set", "sorted", "str", "sum", "tuple", "zip", "map", "filter", "isinstance", "print", "reversed",
    "divmod", "pow", "True", "False", "None", "ValueError", "KeyError", "TypeError", "Exception",
]


class _Checker(ast.NodeVisitor):
    def visit_Import(self, node):
        raise GuardrailError("Imports are not allowed in analysis code")

    def visit_ImportFrom(self, node):
        raise GuardrailError("Imports are not allowed in analysis code")

    def visit_Attribute(self, node):
        a = node.attr
        if a.startswith("_") or a in BANNED_ATTRS or a.startswith(("to_", "read_")):
            raise GuardrailError(f"Attribute `{a}` is not allowed in analysis code")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in BANNED_NAMES or node.id.startswith("__"):
            raise GuardrailError(f"Name `{node.id}` is not allowed in analysis code")
        self.generic_visit(node)


def validate_python(code: str) -> ast.Module:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise GuardrailError(f"Syntax error in generated code: {e}")
    _Checker().visit(tree)
    return tree


def run_python(df: pd.DataFrame, code: str):
    tree = validate_python(code)
    safe = {k: getattr(builtins, k) for k in SAFE_BUILTINS}
    env = {"__builtins__": safe, "df": df.copy(), "pd": pd, "np": np}

    def _exec():
        exec(compile(tree, "<analysis>", "exec"), env)
        if "result" not in env:
            raise GuardrailError("Code must assign the final output to a variable named `result`")
        return env["result"]

    return _with_timeout(_exec)


def _with_timeout(fn):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=EXEC_TIMEOUT)
        except FutureTimeout:
            raise GuardrailError(f"Execution exceeded {EXEC_TIMEOUT}s time limit")


def to_frame(result) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame):
        out = result
        if isinstance(out.index, pd.MultiIndex) or out.index.name is not None or not isinstance(out.index, pd.RangeIndex):
            out = out.reset_index()
    elif isinstance(result, pd.Series):
        out = result.reset_index()
        if out.columns.tolist()[-1] == 0:
            out = out.rename(columns={0: result.name or "value"})
    elif isinstance(result, dict):
        try:
            out = pd.DataFrame(result)
        except ValueError:
            out = pd.DataFrame([result])
    elif isinstance(result, (list, tuple, np.ndarray)):
        out = pd.DataFrame({"value": list(result)})
    else:
        out = pd.DataFrame({"value": [result]})
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" / ".join(str(p) for p in c if str(p)) for c in out.columns]
    out.columns = [str(c) for c in out.columns]
    return out
