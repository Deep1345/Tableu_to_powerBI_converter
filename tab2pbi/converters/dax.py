"""Tableau formula to DAX converter.

Implements a tokenizer and recursive-descent parser that produces
an AST, then emits DAX from the AST. Handles:
- Aggregation functions (SUM, AVG, COUNT, COUNTD, MIN, MAX, ATTR)
- Control flow (IF/THEN/ELSE, CASE/WHEN, IIF)
- String functions (LEFT, RIGHT, MID, CONTAINS, etc.)
- Date functions (DATEPART, DATETRUNC, DATEADD, DATEDIFF)
- Math functions (INT, FLOAT, ROUND, ABS, DIV)
- LOD expressions ({FIXED [A],[B] : AGG(x)})
- Null handling (ZN, IFNULL, ISNULL)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Token types ────────────────────────────────────────────────

class TokenType(Enum):
    NUMBER = auto()
    STRING_LIT = auto()      # "hello" or 'hello'
    FIELD_REF = auto()       # [Field Name]
    IDENT = auto()           # function names, keywords
    LPAREN = auto()          # (
    RPAREN = auto()          # )
    LBRACE = auto()          # {
    RBRACE = auto()          # }
    COMMA = auto()           # ,
    COLON = auto()           # :
    PLUS = auto()            # +
    MINUS = auto()           # -
    STAR = auto()            # *
    SLASH = auto()           # /
    EQ = auto()              # =
    NEQ = auto()             # <> or !=
    LT = auto()              # <
    GT = auto()              # >
    LTE = auto()             # <=
    GTE = auto()             # >=
    AND = auto()
    OR = auto()
    NOT = auto()
    DOT = auto()             # .
    AMPERSAND = auto()       # &
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int = 0


# ─── AST node types ────────────────────────────────────────────

@dataclass
class ASTNode:
    pass


@dataclass
class NumberLiteral(ASTNode):
    value: str = ""


@dataclass
class StringLiteral(ASTNode):
    value: str = ""


@dataclass
class FieldRef(ASTNode):
    name: str = ""           # e.g. "Sales"
    table: str = ""          # Will be filled in during DAX emission


@dataclass
class FunctionCall(ASTNode):
    name: str = ""
    args: list[ASTNode] = field(default_factory=list)


@dataclass
class BinaryOp(ASTNode):
    op: str = ""
    left: Optional[ASTNode] = None
    right: Optional[ASTNode] = None


@dataclass
class UnaryOp(ASTNode):
    op: str = ""
    operand: Optional[ASTNode] = None


@dataclass
class IfExpr(ASTNode):
    """IF cond THEN a ELSEIF cond2 THEN b ELSE c END"""
    condition: Optional[ASTNode] = None
    then_expr: Optional[ASTNode] = None
    elseif_chains: list[tuple[ASTNode, ASTNode]] = field(default_factory=list)
    else_expr: Optional[ASTNode] = None


@dataclass
class CaseExpr(ASTNode):
    """CASE x WHEN v THEN r ... ELSE e END"""
    expr: Optional[ASTNode] = None
    when_clauses: list[tuple[ASTNode, ASTNode]] = field(default_factory=list)
    else_expr: Optional[ASTNode] = None


@dataclass
class LODExpr(ASTNode):
    """{FIXED [A],[B] : AGG(x)}"""
    lod_type: str = "FIXED"  # FIXED, INCLUDE, EXCLUDE
    dimensions: list[FieldRef] = field(default_factory=list)
    expression: Optional[ASTNode] = None


# ─── Tokenizer ─────────────────────────────────────────────────

class Tokenizer:
    """Tokenize a Tableau formula string."""

    KEYWORDS = {
        "AND", "OR", "NOT", "IF", "THEN", "ELSE", "ELSEIF", "END",
        "CASE", "WHEN", "TRUE", "FALSE", "NULL",
        "FIXED", "INCLUDE", "EXCLUDE",
    }

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the full formula text."""
        while self.pos < len(self.text):
            self._skip_whitespace()
            if self.pos >= len(self.text):
                break

            ch = self.text[self.pos]

            # String literals
            if ch == '"':
                self._read_string('"')
            elif ch == "'":
                # Could be a string literal in Tableau
                self._read_string("'")
            # Field references [Name]
            elif ch == '[':
                self._read_field_ref()
            # LOD braces
            elif ch == '{':
                self.tokens.append(Token(TokenType.LBRACE, '{', self.pos))
                self.pos += 1
            elif ch == '}':
                self.tokens.append(Token(TokenType.RBRACE, '}', self.pos))
                self.pos += 1
            # Numbers
            elif ch.isdigit() or (ch == '.' and self.pos + 1 < len(self.text) and self.text[self.pos + 1].isdigit()):
                self._read_number()
            # Identifiers / keywords
            elif ch.isalpha() or ch == '_':
                self._read_identifier()
            # Operators
            elif ch == '(':
                self.tokens.append(Token(TokenType.LPAREN, '(', self.pos))
                self.pos += 1
            elif ch == ')':
                self.tokens.append(Token(TokenType.RPAREN, ')', self.pos))
                self.pos += 1
            elif ch == ',':
                self.tokens.append(Token(TokenType.COMMA, ',', self.pos))
                self.pos += 1
            elif ch == ':':
                self.tokens.append(Token(TokenType.COLON, ':', self.pos))
                self.pos += 1
            elif ch == '+':
                self.tokens.append(Token(TokenType.PLUS, '+', self.pos))
                self.pos += 1
            elif ch == '-':
                self.tokens.append(Token(TokenType.MINUS, '-', self.pos))
                self.pos += 1
            elif ch == '*':
                self.tokens.append(Token(TokenType.STAR, '*', self.pos))
                self.pos += 1
            elif ch == '/':
                self.tokens.append(Token(TokenType.SLASH, '/', self.pos))
                self.pos += 1
            elif ch == '&':
                self.tokens.append(Token(TokenType.AMPERSAND, '&', self.pos))
                self.pos += 1
            elif ch == '.':
                self.tokens.append(Token(TokenType.DOT, '.', self.pos))
                self.pos += 1
            elif ch == '=' :
                self.tokens.append(Token(TokenType.EQ, '=', self.pos))
                self.pos += 1
            elif ch == '<':
                if self.pos + 1 < len(self.text):
                    if self.text[self.pos + 1] == '>':
                        self.tokens.append(Token(TokenType.NEQ, '<>', self.pos))
                        self.pos += 2
                    elif self.text[self.pos + 1] == '=':
                        self.tokens.append(Token(TokenType.LTE, '<=', self.pos))
                        self.pos += 2
                    else:
                        self.tokens.append(Token(TokenType.LT, '<', self.pos))
                        self.pos += 1
                else:
                    self.tokens.append(Token(TokenType.LT, '<', self.pos))
                    self.pos += 1
            elif ch == '>':
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '=':
                    self.tokens.append(Token(TokenType.GTE, '>=', self.pos))
                    self.pos += 2
                else:
                    self.tokens.append(Token(TokenType.GT, '>', self.pos))
                    self.pos += 1
            elif ch == '!':
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '=':
                    self.tokens.append(Token(TokenType.NEQ, '!=', self.pos))
                    self.pos += 2
                else:
                    self.pos += 1  # skip unknown
            else:
                self.pos += 1  # skip unknown characters

        self.tokens.append(Token(TokenType.EOF, '', self.pos))
        return self.tokens

    def _skip_whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t\n\r':
            self.pos += 1

    def _read_string(self, quote: str):
        start = self.pos
        self.pos += 1  # skip opening quote
        value = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == quote:
                self.pos += 1
                # Check for escaped quote (doubled)
                if self.pos < len(self.text) and self.text[self.pos] == quote:
                    value.append(quote)
                    self.pos += 1
                else:
                    break
            elif ch == '\\':
                self.pos += 1
                if self.pos < len(self.text):
                    value.append(self.text[self.pos])
                    self.pos += 1
            else:
                value.append(ch)
                self.pos += 1

        self.tokens.append(Token(TokenType.STRING_LIT, ''.join(value), start))

    def _read_field_ref(self):
        start = self.pos
        self.pos += 1  # skip [
        value = []
        while self.pos < len(self.text) and self.text[self.pos] != ']':
            value.append(self.text[self.pos])
            self.pos += 1
        if self.pos < len(self.text):
            self.pos += 1  # skip ]

        self.tokens.append(Token(TokenType.FIELD_REF, ''.join(value), start))

    def _read_number(self):
        start = self.pos
        value = []
        has_dot = False
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch.isdigit():
                value.append(ch)
                self.pos += 1
            elif ch == '.' and not has_dot:
                has_dot = True
                value.append(ch)
                self.pos += 1
            else:
                break
        self.tokens.append(Token(TokenType.NUMBER, ''.join(value), start))

    def _read_identifier(self):
        start = self.pos
        value = []
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
            value.append(self.text[self.pos])
            self.pos += 1

        ident = ''.join(value)
        upper = ident.upper()

        if upper == "AND":
            self.tokens.append(Token(TokenType.AND, ident, start))
        elif upper == "OR":
            self.tokens.append(Token(TokenType.OR, ident, start))
        elif upper == "NOT":
            self.tokens.append(Token(TokenType.NOT, ident, start))
        else:
            self.tokens.append(Token(TokenType.IDENT, ident, start))


# ─── Parser ────────────────────────────────────────────────────

class Parser:
    """Recursive-descent parser for Tableau formulas."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def parse(self) -> ASTNode:
        """Parse the token stream into an AST."""
        node = self._parse_expression()
        return node

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, '')

    def _peek(self) -> Token:
        return self._current()

    def _advance(self) -> Token:
        tok = self._current()
        self.pos += 1
        return tok

    def _expect(self, ttype: TokenType) -> Token:
        tok = self._current()
        if tok.type != ttype:
            raise ParseError(
                f"Expected {ttype.name}, got {tok.type.name} ('{tok.value}') at pos {tok.pos}"
            )
        return self._advance()

    def _match(self, ttype: TokenType) -> Optional[Token]:
        if self._current().type == ttype:
            return self._advance()
        return None

    def _match_ident(self, *names: str) -> Optional[Token]:
        tok = self._current()
        if tok.type == TokenType.IDENT and tok.value.upper() in [n.upper() for n in names]:
            return self._advance()
        return None

    # ── Expression precedence levels ──

    def _parse_expression(self) -> ASTNode:
        return self._parse_or()

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self._current().type == TokenType.OR:
            self._advance()
            right = self._parse_and()
            left = BinaryOp(op="OR", left=left, right=right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_not()
        while self._current().type == TokenType.AND:
            self._advance()
            right = self._parse_not()
            left = BinaryOp(op="AND", left=left, right=right)
        return left

    def _parse_not(self) -> ASTNode:
        if self._current().type == TokenType.NOT:
            self._advance()
            operand = self._parse_comparison()
            return UnaryOp(op="NOT", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_concat()
        tok = self._current()
        if tok.type in (TokenType.EQ, TokenType.NEQ, TokenType.LT,
                        TokenType.GT, TokenType.LTE, TokenType.GTE):
            op = self._advance().value
            right = self._parse_concat()
            return BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_concat(self) -> ASTNode:
        """Handle string concatenation with + or &."""
        left = self._parse_additive()
        while self._current().type == TokenType.AMPERSAND:
            self._advance()
            right = self._parse_additive()
            left = BinaryOp(op="&", left=left, right=right)
        return left

    def _parse_additive(self) -> ASTNode:
        left = self._parse_multiplicative()
        while self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> ASTNode:
        left = self._parse_unary()
        while self._current().type in (TokenType.STAR, TokenType.SLASH):
            op = self._advance().value
            right = self._parse_unary()
            left = BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_unary(self) -> ASTNode:
        if self._current().type == TokenType.MINUS:
            self._advance()
            operand = self._parse_primary()
            return UnaryOp(op="-", operand=operand)
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        tok = self._current()

        # LOD expression: {FIXED ...}
        if tok.type == TokenType.LBRACE:
            return self._parse_lod()

        # IF expression
        if tok.type == TokenType.IDENT and tok.value.upper() == "IF":
            return self._parse_if()

        # CASE expression
        if tok.type == TokenType.IDENT and tok.value.upper() == "CASE":
            return self._parse_case()

        # IIF function (handle specially)
        if tok.type == TokenType.IDENT and tok.value.upper() == "IIF":
            return self._parse_function_call()

        # Number
        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLiteral(value=tok.value)

        # String literal
        if tok.type == TokenType.STRING_LIT:
            self._advance()
            return StringLiteral(value=tok.value)

        # Field reference [Name]
        if tok.type == TokenType.FIELD_REF:
            self._advance()
            return FieldRef(name=tok.value)

        # TRUE / FALSE
        if tok.type == TokenType.IDENT and tok.value.upper() in ("TRUE", "FALSE"):
            self._advance()
            return NumberLiteral(value=tok.value.upper())

        # NULL
        if tok.type == TokenType.IDENT and tok.value.upper() == "NULL":
            self._advance()
            return FunctionCall(name="BLANK")

        # Function call or identifier
        if tok.type == TokenType.IDENT:
            return self._parse_function_call()

        # Parenthesized expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return expr

        # If nothing matched, advance and return a blank
        self._advance()
        return NumberLiteral(value="0")

    def _parse_function_call(self) -> ASTNode:
        name_tok = self._expect(TokenType.IDENT)

        if self._current().type != TokenType.LPAREN:
            # It's just an identifier, not a function call
            return FieldRef(name=name_tok.value)

        self._advance()  # consume (
        args = []

        if self._current().type != TokenType.RPAREN:
            args.append(self._parse_expression())
            while self._match(TokenType.COMMA):
                args.append(self._parse_expression())

        self._expect(TokenType.RPAREN)
        return FunctionCall(name=name_tok.value, args=args)

    def _parse_if(self) -> ASTNode:
        """Parse IF cond THEN a ELSEIF cond2 THEN b ELSE c END."""
        self._expect(TokenType.IDENT)  # consume IF

        condition = self._parse_expression()
        self._match_ident("THEN")
        then_expr = self._parse_expression()

        elseif_chains = []
        else_expr = None

        while True:
            tok = self._current()
            if tok.type == TokenType.IDENT and tok.value.upper() == "ELSEIF":
                self._advance()
                elif_cond = self._parse_expression()
                self._match_ident("THEN")
                elif_then = self._parse_expression()
                elseif_chains.append((elif_cond, elif_then))
            elif tok.type == TokenType.IDENT and tok.value.upper() == "ELSE":
                self._advance()
                else_expr = self._parse_expression()
            elif tok.type == TokenType.IDENT and tok.value.upper() == "END":
                self._advance()
                break
            else:
                break

        return IfExpr(
            condition=condition,
            then_expr=then_expr,
            elseif_chains=elseif_chains,
            else_expr=else_expr,
        )

    def _parse_case(self) -> ASTNode:
        """Parse CASE x WHEN v THEN r ... ELSE e END."""
        self._expect(TokenType.IDENT)  # consume CASE

        expr = self._parse_expression()
        when_clauses = []
        else_expr = None

        while True:
            tok = self._current()
            if tok.type == TokenType.IDENT and tok.value.upper() == "WHEN":
                self._advance()
                when_val = self._parse_expression()
                self._match_ident("THEN")
                then_val = self._parse_expression()
                when_clauses.append((when_val, then_val))
            elif tok.type == TokenType.IDENT and tok.value.upper() == "ELSE":
                self._advance()
                else_expr = self._parse_expression()
            elif tok.type == TokenType.IDENT and tok.value.upper() == "END":
                self._advance()
                break
            else:
                break

        return CaseExpr(expr=expr, when_clauses=when_clauses, else_expr=else_expr)

    def _parse_lod(self) -> ASTNode:
        """Parse {FIXED [A],[B] : AGG(x)}."""
        self._expect(TokenType.LBRACE)

        lod_type = "FIXED"
        tok = self._current()
        if tok.type == TokenType.IDENT and tok.value.upper() in ("FIXED", "INCLUDE", "EXCLUDE"):
            lod_type = self._advance().value.upper()

        dimensions = []
        # Parse dimension list before the colon
        while self._current().type != TokenType.COLON and self._current().type != TokenType.RBRACE:
            if self._current().type == TokenType.FIELD_REF:
                dimensions.append(FieldRef(name=self._advance().value))
            elif self._current().type == TokenType.COMMA:
                self._advance()
            else:
                break

        self._match(TokenType.COLON)

        # Parse the aggregate expression
        expression = self._parse_expression()

        self._expect(TokenType.RBRACE)

        return LODExpr(lod_type=lod_type, dimensions=dimensions, expression=expression)


class ParseError(Exception):
    """Raised when formula parsing fails."""
    pass


# ─── DAX Emitter ───────────────────────────────────────────────

# Function name mappings: Tableau -> DAX
_FUNC_MAP = {
    "SUM": "SUM",
    "AVG": "AVERAGE",
    "AVERAGE": "AVERAGE",
    "COUNT": "COUNT",
    "COUNTD": "DISTINCTCOUNT",
    "MIN": "MIN",
    "MAX": "MAX",
    "ATTR": "SELECTEDVALUE",
    "MEDIAN": "MEDIAN",

    "ZN": "_ZN",             # Special handling
    "IFNULL": "_IFNULL",     # Special handling
    "ISNULL": "_ISNULL",     # Special handling
    "IIF": "_IIF",           # Special handling

    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "MID": "MID",
    "LEN": "LEN",
    "UPPER": "UPPER",
    "LOWER": "LOWER",
    "TRIM": "TRIM",
    "CONTAINS": "_CONTAINS",
    "STARTSWITH": "_STARTSWITH",
    "REPLACE": "_REPLACE",
    "STR": "_STR",
    "STRING": "_STR",

    "YEAR": "YEAR",
    "MONTH": "MONTH",
    "DAY": "DAY",
    "TODAY": "TODAY",
    "NOW": "NOW",
    "DATEPART": "_DATEPART",
    "DATETRUNC": "_DATETRUNC",
    "DATEADD": "_DATEADD",
    "DATEDIFF": "_DATEDIFF",

    "INT": "INT",
    "FLOAT": "_FLOAT",
    "ROUND": "ROUND",
    "ABS": "ABS",
    "CEILING": "CEILING",
    "FLOOR": "FLOOR",
    "POWER": "POWER",
    "SQRT": "SQRT",
    "LOG": "LOG",
    "LN": "LN",
    "EXP": "EXP",
    "SIGN": "SIGN",
    "DIV": "_DIV",

    "MAKEDATETIME": "DATEVALUE",
    "MAKEDATE": "DATE",
}


class DAXEmitter:
    """Convert a Tableau formula AST to DAX expression."""

    def __init__(self, table_name: str = "Table", columns: dict = None):
        self.table_name = table_name
        self.columns = columns or {}
        self.is_measure = False
        self.unsupported_reason = ""

    def emit(self, node: ASTNode) -> str:
        """Emit DAX from an AST node."""
        if isinstance(node, NumberLiteral):
            return node.value

        if isinstance(node, StringLiteral):
            # DAX uses double quotes for strings
            escaped = node.value.replace('"', '""')
            return f'"{escaped}"'

        if isinstance(node, FieldRef):
            return self._emit_field_ref(node)

        if isinstance(node, FunctionCall):
            return self._emit_function(node)

        if isinstance(node, BinaryOp):
            return self._emit_binary(node)

        if isinstance(node, UnaryOp):
            return self._emit_unary(node)

        if isinstance(node, IfExpr):
            return self._emit_if(node)

        if isinstance(node, CaseExpr):
            return self._emit_case(node)

        if isinstance(node, LODExpr):
            return self._emit_lod(node)

        return "BLANK()"

    def _emit_field_ref(self, node: FieldRef) -> str:
        """Emit a field reference in DAX format."""
        name = node.name
        table = node.table or self.table_name

        # Check if this is a reference to another measure/calc
        ref_key = f"[{name}]"
        if ref_key in self.columns:
            col_info = self.columns[ref_key]
            if col_info.is_calculated:
                return f"[{col_info.caption}]"

        # Regular column reference: 'Table'[Column]
        quoted_table = f"'{table}'" if ' ' in table or table[0].isdigit() else table
        return f"{quoted_table}[{name}]"

    def _emit_function(self, node: FunctionCall) -> str:
        """Emit a function call in DAX."""
        upper_name = node.name.upper()
        dax_name = _FUNC_MAP.get(upper_name, None)

        if dax_name is None:
            # Unknown function - try to pass through
            args_str = ", ".join(self.emit(a) for a in node.args)
            logger.warning(f"Unknown Tableau function: {node.name}")
            return f"{node.name}({args_str})"

        # Handle special functions
        if dax_name == "_ZN":
            # ZN(x) -> COALESCE(x, 0)
            arg = self.emit(node.args[0]) if node.args else "0"
            return f"COALESCE({arg}, 0)"

        if dax_name == "_IFNULL":
            # IFNULL(a, b) -> COALESCE(a, b)
            args = [self.emit(a) for a in node.args]
            return f"COALESCE({', '.join(args)})"

        if dax_name == "_ISNULL":
            # ISNULL(x) -> ISBLANK(x)
            arg = self.emit(node.args[0]) if node.args else "BLANK()"
            return f"ISBLANK({arg})"

        if dax_name == "_IIF":
            # IIF(cond, a, b) -> IF(cond, a, b)
            args = [self.emit(a) for a in node.args]
            return f"IF({', '.join(args)})"

        if dax_name == "_CONTAINS":
            # CONTAINS(string, substring) -> CONTAINSSTRING(string, substring)
            args = [self.emit(a) for a in node.args]
            return f"CONTAINSSTRING({', '.join(args)})"

        if dax_name == "_STARTSWITH":
            # STARTSWITH(s, t) -> LEFT(s, LEN(t)) = t
            if len(node.args) >= 2:
                s = self.emit(node.args[0])
                t = self.emit(node.args[1])
                return f"LEFT({s}, LEN({t})) = {t}"
            return "FALSE"

        if dax_name == "_REPLACE":
            # REPLACE(s, old, new) -> SUBSTITUTE(s, old, new)
            args = [self.emit(a) for a in node.args]
            return f"SUBSTITUTE({', '.join(args)})"

        if dax_name == "_STR":
            # STR(x) -> FORMAT(x, "0")
            arg = self.emit(node.args[0]) if node.args else "0"
            return f'FORMAT({arg}, "0")'

        if dax_name == "_DATEPART":
            # DATEPART('year', d) -> YEAR(d)
            if len(node.args) >= 2:
                part = node.args[0]
                date_expr = self.emit(node.args[1])
                part_str = ""
                if isinstance(part, StringLiteral):
                    part_str = part.value.lower()
                elif isinstance(part, FieldRef):
                    part_str = part.name.lower()

                date_func_map = {
                    "year": "YEAR", "month": "MONTH", "day": "DAY",
                    "quarter": "QUARTER", "weekday": "WEEKDAY",
                    "hour": "HOUR", "minute": "MINUTE", "second": "SECOND",
                    "week": "WEEKNUM",
                }
                func = date_func_map.get(part_str, "YEAR")
                return f"{func}({date_expr})"
            return "BLANK()"

        if dax_name == "_DATETRUNC":
            # DATETRUNC('month', d) -> DATE(YEAR(d), MONTH(d), 1)
            if len(node.args) >= 2:
                part = node.args[0]
                date_expr = self.emit(node.args[1])
                part_str = ""
                if isinstance(part, StringLiteral):
                    part_str = part.value.lower()

                if part_str == "month":
                    return f"DATE(YEAR({date_expr}), MONTH({date_expr}), 1)"
                elif part_str == "year":
                    return f"DATE(YEAR({date_expr}), 1, 1)"
                elif part_str == "quarter":
                    return (f"DATE(YEAR({date_expr}), "
                           f"(QUARTER({date_expr}) - 1) * 3 + 1, 1)")
                elif part_str == "day":
                    return date_expr
                elif part_str == "week":
                    return f"{date_expr} - WEEKDAY({date_expr}, 2) + 1"
            return "BLANK()"

        if dax_name == "_DATEADD":
            # DATEADD('day', n, d) -> d + n  (simplified)
            if len(node.args) >= 3:
                part = node.args[0]
                n = self.emit(node.args[1])
                d = self.emit(node.args[2])
                part_str = ""
                if isinstance(part, StringLiteral):
                    part_str = part.value.lower()

                if part_str == "day":
                    return f"{d} + {n}"
                elif part_str == "month":
                    return f"EDATE({d}, {n})"
                elif part_str == "year":
                    return f"EDATE({d}, {n} * 12)"
            return "BLANK()"

        if dax_name == "_DATEDIFF":
            # DATEDIFF('day', a, b) -> DATEDIFF(a, b, DAY)
            if len(node.args) >= 3:
                part = node.args[0]
                a = self.emit(node.args[1])
                b = self.emit(node.args[2])
                part_str = ""
                if isinstance(part, StringLiteral):
                    part_str = part.value.upper()

                part_map = {
                    "DAY": "DAY", "MONTH": "MONTH", "YEAR": "YEAR",
                    "QUARTER": "QUARTER", "WEEK": "WEEK",
                    "HOUR": "HOUR", "MINUTE": "MINUTE", "SECOND": "SECOND",
                }
                dax_part = part_map.get(part_str, "DAY")
                return f"DATEDIFF({a}, {b}, {dax_part})"
            return "BLANK()"

        if dax_name == "_FLOAT":
            # FLOAT(x) -> CONVERT(x, DOUBLE)
            arg = self.emit(node.args[0]) if node.args else "0"
            return f"CONVERT({arg}, DOUBLE)"

        if dax_name == "_DIV":
            # DIV(a, b) -> QUOTIENT(a, b)
            args = [self.emit(a) for a in node.args]
            return f"QUOTIENT({', '.join(args)})"

        # Standard function mapping
        args_str = ", ".join(self.emit(a) for a in node.args)
        if not node.args:
            return f"{dax_name}()"
        return f"{dax_name}({args_str})"

    def _emit_binary(self, node: BinaryOp) -> str:
        """Emit a binary operation in DAX."""
        left = self.emit(node.left)
        right = self.emit(node.right)

        if node.op == "AND":
            return f"({left}) && ({right})"
        elif node.op == "OR":
            return f"({left}) || ({right})"
        elif node.op == "&":
            return f"{left} & {right}"
        elif node.op == "/" and self.is_measure:
            return f"DIVIDE({left}, {right})"
        else:
            return f"{left} {node.op} {right}"

    def _emit_unary(self, node: UnaryOp) -> str:
        """Emit a unary operation in DAX."""
        operand = self.emit(node.operand)
        if node.op == "NOT":
            return f"NOT({operand})"
        elif node.op == "-":
            return f"-{operand}"
        return operand

    def _emit_if(self, node: IfExpr) -> str:
        """Emit IF expression in DAX.
        IF c THEN a ELSEIF c2 THEN b ELSE d END
        -> IF(c, a, IF(c2, b, d))
        """
        cond = self.emit(node.condition)
        then = self.emit(node.then_expr)

        if not node.elseif_chains and not node.else_expr:
            return f"IF({cond}, {then})"

        # Build nested IF for ELSEIF chains
        else_part = self.emit(node.else_expr) if node.else_expr else "BLANK()"

        # Work backwards through elseif chains
        for elif_cond, elif_then in reversed(node.elseif_chains):
            elif_cond_str = self.emit(elif_cond)
            elif_then_str = self.emit(elif_then)
            else_part = f"IF({elif_cond_str}, {elif_then_str}, {else_part})"

        return f"IF({cond}, {then}, {else_part})"

    def _emit_case(self, node: CaseExpr) -> str:
        """Emit CASE expression as SWITCH in DAX.
        CASE x WHEN v THEN r ... ELSE e END
        -> SWITCH(x, v, r, ..., e)
        """
        expr = self.emit(node.expr)
        parts = [expr]

        for when_val, then_val in node.when_clauses:
            parts.append(self.emit(when_val))
            parts.append(self.emit(then_val))

        if node.else_expr:
            parts.append(self.emit(node.else_expr))

        return f"SWITCH({', '.join(parts)})"

    def _emit_lod(self, node: LODExpr) -> str:
        """Emit LOD expression as CALCULATE in DAX.
        {FIXED [A],[B] : AGG(x)}
        -> CALCULATE(AGG(x), ALLEXCEPT('Table', 'Table'[A], 'Table'[B]))

        {FIXED : AGG(x)}
        -> CALCULATE(AGG(x), ALL('Table'))
        """
        self.is_measure = True
        agg_expr = self.emit(node.expression)
        table = f"'{self.table_name}'" if ' ' in self.table_name else self.table_name

        if not node.dimensions:
            # {FIXED : AGG(x)} -> no dimensions, use ALL
            return f"CALCULATE({agg_expr}, ALL({table}))"
        else:
            dim_refs = ", ".join(
                f"{table}[{d.name}]" for d in node.dimensions
            )
            return f"CALCULATE({agg_expr}, ALLEXCEPT({table}, {dim_refs}))"


# ─── Public API ─────────────────────────────────────────────────

def convert_formula(
    formula: str,
    table_name: str = "Table",
    columns: dict = None,
) -> tuple[str, str, str]:
    """Convert a Tableau formula to DAX.

    Args:
        formula: The Tableau formula string.
        table_name: Name of the table for column references.
        columns: Dictionary of column info for reference resolution.

    Returns:
        Tuple of (dax_expression, calc_type, status) where:
        - dax_expression is the DAX string
        - calc_type is 'measure' or 'column'
        - status is 'converted' or 'unsupported'
    """
    if not formula or not formula.strip():
        return "BLANK()", "measure", "converted"

    from tab2pbi.parser.calculations import classify_calculation

    calc_type = classify_calculation(formula)

    try:
        tokenizer = Tokenizer(formula)
        tokens = tokenizer.tokenize()

        parser = Parser(tokens)
        ast = parser.parse()

        emitter = DAXEmitter(table_name=table_name, columns=columns or {})
        emitter.is_measure = (calc_type == "measure")

        dax = emitter.emit(ast)

        # Validate basic DAX structure
        if not dax or dax.isspace():
            dax = "BLANK()"

        return dax, calc_type, "converted"

    except Exception as e:
        logger.warning(f"Failed to convert formula: {formula} -> {e}")
        return "BLANK()", calc_type, "unsupported"
