"""Lex and parse the supported C subset with Lark."""

from pathlib import Path

from lark import Lark, Token, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedToken, VisitError
from lark.visitors import Transformer_NonRecursive

from .model import Diagnostic, Node, Span


_GRAMMAR = Path(__file__).with_name("c_subset.lark")
_PARSER = Lark.open(str(_GRAMMAR), parser="lalr", lexer="basic", propagate_positions=True)

_C_KEYWORDS = frozenset(
    """
    auto break case char const continue default do double else enum extern float
    for goto if inline int long register restrict return short signed sizeof static
    struct switch typedef union unsigned void volatile while _Alignas _Alignof
    _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local
    """.split()
)

_TOKEN_NAMES = {
    "$END": "кінець файлу",
    "_INT": "'int'",
    "_VOID": "'void'",
    "_IF": "'if'",
    "_ELSE": "'else'",
    "_WHILE": "'while'",
    "_RETURN": "'return'",
    "IDENTIFIER": "ідентифікатор",
    "DECIMAL": "ціле число",
    "EQUALITY": "'==' або '!='",
    "COMPARISON": "оператор порівняння",
    "ADDITIVE": "'+' або '-'",
    "MULTIPLICATIVE": "'*', '/' або '%'",
    "LPAR": "'('",
    "RPAR": "')'",
    "LBRACE": "'{'",
    "RBRACE": "'}'",
    "LSQB": "'['",
    "RSQB": "']'",
    "COMMA": "','",
    "SEMICOLON": "';'",
    "EQUAL": "'='",
}


def _span(position):
    return Span(position.line, position.column, position.end_line, position.end_column)


def _variable(token: Token) -> Node:
    name = str(token)
    span = _span(token)
    if name in _C_KEYWORDS:
        raise Diagnostic("syntax", f"Ключове слово {name!r} не може бути ідентифікатором.", span)
    return Node("variable", span, name)


@v_args(meta=True)
class _BuildAST(Transformer_NonRecursive):
    def function(self, meta, children):
        name, body = children
        if name != "main":
            raise Diagnostic("syntax", "Підтримується лише функція 'main'.", _span(name))
        return Node("function", _span(meta), str(name), (body,))

    def block(self, meta, children):
        return Node("block", _span(meta), children=tuple(children))

    def declare(self, meta, children):
        return Node("declare", _span(meta), children=tuple(children))

    def declare_array(self, meta, children):
        return Node("declare_array", _span(meta), children=tuple(children))

    def initializer_list(self, meta, children):
        return Node("initializer_list", _span(meta), children=tuple(children))

    def assign(self, meta, children):
        return Node("assign", _span(meta), children=tuple(children))

    def index(self, meta, children):
        return Node("index", _span(meta), children=tuple(children))

    def return_statement(self, meta, children):
        return Node("return", _span(meta), children=tuple(children))

    def if_statement(self, meta, children):
        return Node("if", _span(meta), children=tuple(children))

    def while_statement(self, meta, children):
        return Node("while", _span(meta), children=tuple(children))

    def binary(self, meta, children):
        left, operator, right = children
        return Node("binary", _span(meta), str(operator), (left, right))

    def unary_operation(self, meta, children):
        operator, expression = children
        return Node("unary", _span(meta), str(operator), (expression,))

    def integer(self, meta, children):
        (token,) = children
        try:
            value = int(token)
        except ValueError as error:
            raise Diagnostic("lexical", "Занадто довгий цілий літерал.", _span(token)) from error
        return Node("integer", _span(meta), value)

    def variable(self, meta, children):
        (token,) = children
        return _variable(token)


def parse(source: str) -> Node:
    """Return an AST or raise a diagnostic with a 1-based source span."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    splice = source.find("\\\n")
    if splice != -1:
        line = source.count("\n", 0, splice) + 1
        column = splice - source.rfind("\n", 0, splice)
        span = Span(line, column, line, column + 1)
        raise Diagnostic("lexical", "Продовження рядка зворотною скісною рискою не підтримується.", span)
    try:
        return _BuildAST().transform(_PARSER.parse(source))
    except UnexpectedCharacters as error:
        position = error.pos_in_stream
        if source.startswith("/*", position):
            message = "Незакритий багаторядковий коментар."
        elif "0" <= source[position] <= "9":
            message = "Очікується десятковий цілий літерал без суфікса й початкових нулів."
        else:
            message = f"Непідтримуваний символ {source[position]!r}."
        span = Span(error.line, error.column, error.line, error.column + 1)
        raise Diagnostic("lexical", message, span) from None
    except UnexpectedToken as error:
        token = error.token
        if token.type == "$END":
            line = source.count("\n") + 1
            column = len(source.rsplit("\n", 1)[-1]) + 1
            span = Span(line, column, line, column)
            found = "Неочікуваний кінець файлу"
        else:
            span = _span(token)
            found = f"Неочікуваний токен {str(token)!r}"
        expected = ", ".join(sorted(_TOKEN_NAMES[name] for name in error.expected if name in _TOKEN_NAMES))
        message = f"{found}. Очікувалося: {expected}." if expected else f"{found}."
        raise Diagnostic("syntax", message, span) from None
    except VisitError as error:
        if isinstance(error.orig_exc, Diagnostic):
            raise error.orig_exc from None
        raise
