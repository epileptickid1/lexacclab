import argparse
import json
import shutil
import sys
from pathlib import Path

from .backend import emit_rust
from .model import Diagnostic
from .parser import parse


def format_diagnostic(error: Diagnostic, path: Path, source: str) -> str:
    stages = {"lexical": "Лексична", "syntax": "Синтаксична", "semantic": "Семантична"}
    span = error.span
    line = source.split("\n")[span.line - 1]
    start = len(line[:span.column - 1].expandtabs(4))
    end_column = span.end_column - 1 if span.end_line == span.line else len(line)
    width = max(1, len(line[:end_column].expandtabs(4)) - start)
    return (
        f"{path}:{span.line}:{span.column}: {stages[error.stage]} помилка. {error.message}\n"
        f"{line.expandtabs(4)}\n{' ' * start}{'^' * width}"
    )


def write_outputs(source: Path, directory: Path, rust: str, ast: str) -> tuple[Path, Path]:
    rust_path = directory / f"{source.stem}.rs"
    ast_path = directory / f"{source.stem}.ast.json"
    for target in (rust_path, ast_path):
        if target.resolve() == source.resolve():
            raise OSError(f"Шлях вихідного файлу збігається з вхідним: {target}")
        if target.exists() and not target.is_file():
            raise OSError(f"Потрібен шлях до звичайного файлу: {target}")

    directory.mkdir(parents=True, exist_ok=True)
    # Creating this directory also serializes writers targeting the same pair.
    staging = directory / f".{source.stem}.lexacc-tmp"
    try:
        staging.mkdir()
    except FileExistsError:
        raise OSError(f"Тимчасовий каталог результатів уже існує: {staging}") from None

    staged_rust = staging / "new.rs"
    staged_ast = staging / "new.json"
    previous_rust = staging / "previous.rs"
    try:
        staged_rust.write_text(rust, encoding="utf-8", newline="\n")
        staged_ast.write_text(ast, encoding="utf-8", newline="\n")
        if rust_path.exists():
            shutil.copyfile(rust_path, previous_rust)
        staged_rust.replace(rust_path)
        try:
            staged_ast.replace(ast_path)
        except OSError:
            if previous_rust.exists():
                previous_rust.replace(rust_path)
            else:
                rust_path.unlink()
            raise
    finally:
        for temporary in (staged_rust, staged_ast, previous_rust):
            temporary.unlink(missing_ok=True)
        staging.rmdir()
    return rust_path, ast_path


def main() -> int:
    cli = argparse.ArgumentParser(
        prog="python -m lexacc",
        description="Трансляція підмножини C у Rust та експорт AST для перегляду в браузері.",
    )
    cli.add_argument("source", type=Path, metavar="FILE.c", help="вхідний файл C у UTF-8")
    cli.add_argument("-o", "--out-dir", type=Path, default=Path("build"), metavar="DIR",
                     help="каталог для .rs та .ast.json (типово build)")
    args = cli.parse_args()

    try:
        source = args.source.read_text(encoding="utf-8-sig")
        root = parse(source)
        rust = emit_rust(root)
        document = {"file": args.source.name, "source": source, "ast": root.to_dict()}
        ast = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        rust_path, ast_path = write_outputs(args.source, args.out_dir, rust, ast)
    except Diagnostic as error:
        print(format_diagnostic(error, args.source, source), file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print(f"{args.source}: очікується текст у UTF-8.", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Помилка роботи з файлами. {error}", file=sys.stderr)
        return 1
    except RecursionError:
        print(f"{args.source}: дерево перевищує доступну глибину обробки.", file=sys.stderr)
        return 1

    print(f"Rust: {rust_path}\nAST:  {ast_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
