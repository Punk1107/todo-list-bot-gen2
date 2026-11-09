"""
search_recommendation/boolean_parser.py — Multi-Tag Boolean & Attribute Search Parser.

Implements a recursive descent parser that compiles complex boolean queries with
tag and attribute filters into SQL-injection safe, parameterized PostgreSQL expressions.

Supported Syntax:
  - Boolean Operators: AND, OR, NOT, (), and implicit AND between terms.
  - Attributes:
      tag:backend / tags:urgent
      priority:p6 / priority:7 / priority:>=5 / priority:critical
      status:completed / status:pending / status:in_progress
      assignee:@123 / assignee:alice
      due:<=today / due:<tomorrow / due:>today / due:2026-11-10
      has:attachment / has:checklist / has:subtasks
      project:42 / project:"Core Engine"
  - Free text keywords: login, "database connection"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Optional


class TokenType(Enum):
    AND = auto()
    OR = auto()
    NOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    ATTR = auto()
    WORD = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str


def tokenize(text: str) -> list[Token]:
    """Tokenizes a search query string into lexical tokens."""
    tokens: list[Token] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch == "(":
            tokens.append(Token(TokenType.LPAREN, "("))
            i += 1
            continue

        if ch == ")":
            tokens.append(Token(TokenType.RPAREN, ")"))
            i += 1
            continue

        # Quoted string
        if ch in ('"', "'"):
            quote_char = ch
            start = i + 1
            i += 1
            while i < n and text[i] != quote_char:
                i += 1
            val = text[start:i]
            if i < n and text[i] == quote_char:
                i += 1
            tokens.append(Token(TokenType.WORD, val))
            continue

        # Extract continuous word/token
        start = i
        while i < n and not text[i].isspace() and text[i] not in ("(", ")"):
            i += 1
        raw = text[start:i]
        upper = raw.upper()

        if upper == "AND":
            tokens.append(Token(TokenType.AND, "AND"))
        elif upper == "OR":
            tokens.append(Token(TokenType.OR, "OR"))
        elif upper == "NOT":
            tokens.append(Token(TokenType.NOT, "NOT"))
        elif ":" in raw:
            tokens.append(Token(TokenType.ATTR, raw))
        else:
            tokens.append(Token(TokenType.WORD, raw))

    tokens.append(Token(TokenType.EOF, ""))
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# AST Nodes
# ─────────────────────────────────────────────────────────────────────────────

class ASTNode:
    """Base class for Boolean Search AST nodes."""
    def to_sql(self, params: list[Any]) -> str:
        raise NotImplementedError


class AndNode(ASTNode):
    def __init__(self, left: ASTNode, right: ASTNode) -> None:
        self.left = left
        self.right = right

    def to_sql(self, params: list[Any]) -> str:
        return f"({self.left.to_sql(params)} AND {self.right.to_sql(params)})"


class OrNode(ASTNode):
    def __init__(self, left: ASTNode, right: ASTNode) -> None:
        self.left = left
        self.right = right

    def to_sql(self, params: list[Any]) -> str:
        return f"({self.left.to_sql(params)} OR {self.right.to_sql(params)})"


class NotNode(ASTNode):
    def __init__(self, child: ASTNode) -> None:
        self.child = child

    def to_sql(self, params: list[Any]) -> str:
        return f"(NOT {self.child.to_sql(params)})"


class TermNode(ASTNode):
    def __init__(self, sql_template: str, val: Any) -> None:
        self.sql_template = sql_template
        self.val = val

    def to_sql(self, params: list[Any]) -> str:
        params.append(self.val)
        idx = len(params)
        return self.sql_template.replace("?", f"${idx}")


class RawConditionNode(ASTNode):
    def __init__(self, sql_str: str) -> None:
        self.sql_str = sql_str

    def to_sql(self, params: list[Any]) -> str:
        return self.sql_str


# ─────────────────────────────────────────────────────────────────────────────
# Recursive Descent Parser
# ─────────────────────────────────────────────────────────────────────────────

class BooleanSearchParser:
    """
    Parses token stream into an AST:
      Expr     := OrExpr
      OrExpr   := AndExpr ( 'OR' AndExpr )*
      AndExpr  := NotExpr ( 'AND'? NotExpr )*
      NotExpr  := 'NOT' NotExpr | Primary
      Primary  := '(' Expr ')' | Term
    """

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else Token(TokenType.EOF, "")

    def advance(self) -> Token:
        tok = self.current()
        if self.pos < len(self.tokens):
            self.pos += 1
        return tok

    def parse(self) -> Optional[ASTNode]:
        if self.current().type == TokenType.EOF:
            return None
        return self.parse_expr()

    def parse_expr(self) -> ASTNode:
        return self.parse_or()

    def parse_or(self) -> ASTNode:
        node = self.parse_and()
        while self.current().type == TokenType.OR:
            self.advance()  # consume OR
            right = self.parse_and()
            node = OrNode(node, right)
        return node

    def parse_and(self) -> ASTNode:
        node = self.parse_not()
        while self.current().type in (TokenType.AND, TokenType.ATTR, TokenType.WORD, TokenType.NOT, TokenType.LPAREN):
            if self.current().type == TokenType.AND:
                self.advance()  # consume explicit AND
            right = self.parse_not()
            node = AndNode(node, right)
        return node

    def parse_not(self) -> ASTNode:
        if self.current().type == TokenType.NOT:
            self.advance()  # consume NOT
            child = self.parse_not()
            return NotNode(child)
        return self.parse_primary()

    def parse_primary(self) -> ASTNode:
        tok = self.current()

        if tok.type == TokenType.LPAREN:
            self.advance()  # consume '('
            node = self.parse_expr()
            if self.current().type == TokenType.RPAREN:
                self.advance()  # consume ')'
            return node

        if tok.type == TokenType.ATTR:
            self.advance()
            return self._parse_attr_term(tok.value)

        if tok.type == TokenType.WORD:
            self.advance()
            val = f"%{tok.value}%"
            # Matches against title or description
            return TermNode("(t.task ILIKE ? OR (t.description IS NOT NULL AND t.description ILIKE ?))", val)

        # Fallback for unexpected token
        self.advance()
        return RawConditionNode("TRUE")

    def _parse_attr_term(self, raw: str) -> ASTNode:
        key, val = raw.split(":", 1)
        key = key.lower()
        val = val.strip().strip('"\'')

        # 1. Tag / Tags
        if key in ("tag", "tags"):
            return TermNode("t.tags ILIKE ?", f"%{val}%")

        # 2. Priority
        if key == "priority":
            p_val = _parse_priority_val(val)
            op = "="
            if val.startswith((">=", "<=", ">", "<")):
                op = re.match(r"(>=|<=|>|<)", val).group(1)
            return TermNode(f"t.priority {op} ?", p_val)

        # 3. Status
        if key == "status":
            s_map = {
                "pending": "Pending",
                "in_progress": "In_Progress",
                "in-progress": "In_Progress",
                "progress": "In_Progress",
                "completed": "Completed",
                "done": "Completed",
                "cancelled": "Cancelled",
            }
            mapped_status = s_map.get(val.lower(), val.capitalize())
            return TermNode("t.status = ?", mapped_status)

        # 4. Assignee / Owner
        if key in ("assignee", "owner"):
            cleaned_id = re.sub(r"[<@!>]", "", val)
            return TermNode("t.owner_id = ?", cleaned_id)

        # 5. Due (Deadline)
        if key in ("due", "deadline"):
            return _parse_due_term(val)

        # 6. Has (attachment, checklist, subtasks)
        if key == "has":
            h_val = val.lower()
            if h_val in ("attachment", "attachments", "file"):
                return RawConditionNode("EXISTS (SELECT 1 FROM task_attachments a WHERE a.task_id = t.task_id)")
            elif h_val in ("checklist", "checklists", "dod"):
                return RawConditionNode("EXISTS (SELECT 1 FROM task_checklists c WHERE c.task_id = t.task_id)")
            elif h_val in ("subtask", "subtasks"):
                return RawConditionNode("EXISTS (SELECT 1 FROM tasks st WHERE st.parent_task_id = t.task_id)")

        # 7. Project
        if key == "project":
            if val.isdigit():
                return TermNode("t.project_id = ?", int(val))
            else:
                return TermNode("EXISTS (SELECT 1 FROM projects p WHERE p.project_id = t.project_id AND p.name ILIKE ?)", f"%{val}%")

        # Fallback: treat as free text
        return TermNode("(t.task ILIKE ? OR (t.description IS NOT NULL AND t.description ILIKE ?))", f"%{raw}%")


def _parse_priority_val(raw_val: str) -> int:
    val_clean = re.sub(r"^[<>=!]+", "", raw_val).strip().lower()
    p_map = {
        "p0": 0, "p1": 1, "p2": 2, "p3": 3, "p4": 4, "p5": 5, "p6": 6, "p7": 7,
        "low": 1, "medium": 3, "high": 5, "critical": 7, "urgent": 7,
    }
    if val_clean in p_map:
        return p_map[val_clean]
    try:
        return max(0, min(7, int(val_clean)))
    except ValueError:
        return 0


def _parse_due_term(val: str) -> ASTNode:
    op = "<="
    match_op = re.match(r"^(<=|>=|<|>|=)", val)
    if match_op:
        op = match_op.group(1)
        val = val[len(op):].strip()

    now_utc = datetime.now(timezone.utc)
    if val.lower() == "today":
        target = now_utc.replace(hour=23, minute=59, second=59)
    elif val.lower() == "tomorrow":
        target = (now_utc + timedelta(days=1)).replace(hour=23, minute=59, second=59)
    else:
        try:
            target = datetime.fromisoformat(val)
        except Exception:
            target = now_utc

    return TermNode(f"t.deadline {op} ?", target.isoformat())


def compile_boolean_query(query_text: str, base_params: Optional[list[Any]] = None) -> tuple[str, list[Any]]:
    """
    Parses a boolean query string and compiles it into a parameterized SQL condition.
    Returns: (sql_condition_string, params_list)
    """
    tokens = tokenize(query_text)
    parser = BooleanSearchParser(tokens)
    ast = parser.parse()

    params = list(base_params) if base_params else []
    if not ast:
        return "TRUE", params

    sql_cond = ast.to_sql(params)
    return sql_cond, params

