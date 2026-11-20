"""Validate the supported C subset and emit Rust source."""

from .model import Diagnostic, Node

_MAX_INT = 2**31 - 1
_ARITHMETIC = {
    "+": "wrapping_add",
    "-": "wrapping_sub",
    "*": "wrapping_mul",
    "/": "wrapping_div",
    "%": "wrapping_rem",
}
_COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


def _rust_name(name: str) -> str:
    # The lexer accepts ASCII C identifiers. The prefix avoids Rust keywords.
    return f"c_{name}"


def emit_rust(root: Node) -> str:
    """Return a standalone Rust program or raise a semantic diagnostic."""
    emitter = _Emitter()
    emitter.lines.append("fn c_main() -> i32 {")
    body = root.children[0]
    emitter.block(body, depth=1)
    if not body.children or body.children[-1].kind != "return":
        emitter.line(1, "0")
    emitter.lines.extend(("}", "", "fn main() {", "    std::process::exit(c_main());", "}"))
    if emitter.uses_subscripts:
        # Keep runtime bounds checks without rejecting dead C branches.
        emitter.lines.insert(0, "#[allow(unconditional_panic)]")
    return "\n".join(emitter.lines) + "\n"


class _Emitter:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.scopes: list[dict[str, str | None]] = []
        self.uses_subscripts = False

    def line(self, depth: int, source: str) -> None:
        self.lines.append("    " * depth + source)

    def block(self, block: Node, depth: int) -> None:
        self.scopes.append({})
        for statement in block.children:
            self.statement(statement, depth)
        self.scopes.pop()

    def body(self, body: Node, depth: int) -> None:
        if body.kind == "block":
            self.block(body, depth)
        else:
            self.statement(body, depth)

    def variable(self, node: Node, kind: str = "int") -> str:
        name = str(node.value)
        for scope in reversed(self.scopes):
            if name in scope:
                if scope[name] is None:
                    raise Diagnostic(
                        "semantic", f"Змінна «{name}» ще не ініціалізована", node.span
                    )
                if scope[name] != kind:
                    if kind == "array":
                        message = f"Змінна «{name}» не є масивом"
                    else:
                        message = f"Для масиву «{name}» потрібно вказати індекс"
                    raise Diagnostic("semantic", message, node.span)
                return _rust_name(name)
        raise Diagnostic("semantic", f"Змінну «{name}» не оголошено", node.span)

    def subscript(self, node: Node) -> str:
        base, index = node.children
        array = self.variable(base, "array")
        self.uses_subscripts = True
        return f"{array}[({self.expression(index)}) as usize]"

    def declaration(self, node: Node, depth: int) -> None:
        target, *initialization = node.children
        name = str(target.value)
        scope = self.scopes[-1]
        if name in scope:
            raise Diagnostic(
                "semantic", f"Повторне оголошення змінної «{name}»", target.span
            )
        scope[name] = None
        rust_name = _rust_name(name)
        if node.kind == "declare":
            (initializer,) = initialization
            value = self.expression(initializer)
            self.line(depth, f"let mut {rust_name}: i32 = {value};")
            scope[name] = "int"
            return

        size, initializer_list = initialization
        if size.kind != "integer" or not 0 < int(size.value) <= _MAX_INT:
            raise Diagnostic(
                "semantic", "Розмір масиву має бути додатною цілою константою типу int", size.span
            )
        length = int(size.value)
        if len(initializer_list.children) > length:
            raise Diagnostic(
                "semantic",
                f"Забагато значень для ініціалізації масиву «{name}»",
                initializer_list.children[length].span,
            )
        self.line(depth, f"let mut {rust_name}: [i32; {length}] = [0; {length}];")
        for index, initializer in enumerate(initializer_list.children):
            self.line(depth, f"{rust_name}[{index}] = {self.expression(initializer)};")
        scope[name] = "array"

    def statement(self, node: Node, depth: int) -> None:
        match node.kind:
            case "block":
                self.line(depth, "{")
                self.block(node, depth + 1)
                self.line(depth, "}")
            case "declare" | "declare_array":
                self.declaration(node, depth)
            case "assign":
                target, expression = node.children
                place = self.subscript(target) if target.kind == "index" else self.variable(target)
                self.line(depth, f"{place} = {self.expression(expression)};")
            case "return":
                self.line(depth, f"return {self.expression(node.children[0])};")
            case "if" | "while":
                condition, body, *otherwise = node.children
                self.line(depth, f"{node.kind} {self.condition(condition)} {{")
                self.body(body, depth + 1)
                if otherwise:
                    self.line(depth, "} else {")
                    self.body(otherwise[0], depth + 1)
                self.line(depth, "}")
            case _:
                raise ValueError(f"Unexpected statement node: {node.kind}")

    def comparison(self, node: Node) -> str:
        left, right = (self.expression(child) for child in node.children)
        return f"{left} {node.value} {right}"

    def condition(self, node: Node) -> str:
        if node.kind == "binary" and node.value in _COMPARISONS:
            return self.comparison(node)
        return f"{self.expression(node)} != 0"

    def expression(self, node: Node) -> str:
        match node.kind:
            case "integer":
                if not 0 <= int(node.value) <= _MAX_INT:
                    raise Diagnostic(
                        "semantic", "Ціла константа виходить за межі типу int", node.span
                    )
                return f"{node.value}i32"
            case "variable":
                return self.variable(node)
            case "index":
                return self.subscript(node)
            case "unary":
                (operand,) = node.children
                if node.value == "-":
                    return f"{self.expression(operand)}.wrapping_neg()"
                return self.expression(operand)
            case "binary":
                if node.value in _COMPARISONS:
                    return f"i32::from({self.comparison(node)})"
                left, right = (self.expression(child) for child in node.children)
                # Runtime methods avoid compile-time errors for dead C branches.
                return f"{left}.{_ARITHMETIC[node.value]}({right})"
            case _:
                raise ValueError(f"Unexpected expression node: {node.kind}")
