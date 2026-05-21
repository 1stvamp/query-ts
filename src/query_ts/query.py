"""Query DSL parser and resource matcher.

Grammar:
    query    := or_expr EOF
    or_expr  := and_expr (OR and_expr)*
    and_expr := not_expr (AND? not_expr)*   -- AND is explicit or implicit (whitespace)
    not_expr := '-' atom | atom
    atom     := '(' or_expr ')' | term
    term     := TAG | WORD

Tag patterns:
    tag:env-production  -> match tag "env-production" exactly (glob allowed)
    env:production      -> match tag "env-production" (prefix-suffix, glob allowed)
    env:prod*           -> match tags "env-prod*"

Name patterns (WORD tokens):
    my-device*          -> fnmatch against hostname / FQDN short name
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


class TokenType(Enum):
    WORD = auto()
    TAG = auto()
    AND = auto()
    OR = auto()
    LPAREN = auto()
    RPAREN = auto()
    NOT = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str


def tokenize(text: str) -> list[Token]:
    """Lex a query string into tokens."""
    tokens: list[Token] = []
    i = 0
    n = len(text)
    # Track whether the previous non-whitespace character ended a "word"
    # so we know if a '-' is negation or part of a word.
    prev_was_word = False

    while i < n:
        ch = text[i]

        if ch.isspace():
            prev_was_word = False
            i += 1
            continue

        if ch == "(":
            tokens.append(Token(TokenType.LPAREN, "("))
            prev_was_word = False
            i += 1
            continue

        if ch == ")":
            tokens.append(Token(TokenType.RPAREN, ")"))
            prev_was_word = True
            i += 1
            continue

        # '-' is negation only when it starts a new term (not inside a word)
        if ch == "-" and not prev_was_word:
            tokens.append(Token(TokenType.NOT, "-"))
            prev_was_word = False
            i += 1
            continue

        # Read a word: everything up to whitespace or ( or )
        # Hyphens are allowed inside words (my-device) but not as a leading char
        j = i
        while j < n and not text[j].isspace() and text[j] not in "()":
            j += 1
        word = text[i:j]
        i = j
        prev_was_word = True

        upper = word.upper()
        if upper == "AND":
            tokens.append(Token(TokenType.AND, word))
        elif upper == "OR":
            tokens.append(Token(TokenType.OR, word))
        elif ":" in word:
            tokens.append(Token(TokenType.TAG, word))
        else:
            tokens.append(Token(TokenType.WORD, word))

    tokens.append(Token(TokenType.EOF, ""))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class Node:
    pass


@dataclass(frozen=True)
class AndNode(Node):
    left: Node
    right: Node


@dataclass(frozen=True)
class OrNode(Node):
    left: Node
    right: Node


@dataclass(frozen=True)
class NotNode(Node):
    operand: Node


@dataclass(frozen=True)
class NamePattern(Node):
    """Glob pattern matched against resource name / hostname."""

    pattern: str


@dataclass(frozen=True)
class TagPattern(Node):
    """Tag filter.  prefix='tag', suffix='env-prod'  OR  prefix='env', suffix='prod'."""

    prefix: str
    suffix: str

    @property
    def normalized(self) -> str:
        """Return the canonical tag name (without the 'tag:' API prefix)."""
        if self.prefix.lower() == "tag":
            return self.suffix
        return f"{self.prefix}-{self.suffix}" if self.suffix else self.prefix


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ParseError(Exception):
    pass


class QueryParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def consume(self, expected: TokenType | None = None) -> Token:
        tok = self.current
        if expected is not None and tok.type != expected:
            raise ParseError(
                f"Expected {expected.name}, got {tok.type.name} ({tok.value!r})"
            )
        self.pos += 1
        return tok

    def parse(self) -> Node | None:
        if self.current.type == TokenType.EOF:
            return None
        node = self._parse_or()
        self.consume(TokenType.EOF)
        return node

    def _parse_or(self) -> Node:
        left = self._parse_and()
        while self.current.type == TokenType.OR:
            self.consume()
            right = self._parse_and()
            left = OrNode(left, right)
        return left

    def _parse_and(self) -> Node:
        left = self._parse_not()
        while self.current.type not in (
            TokenType.OR,
            TokenType.RPAREN,
            TokenType.EOF,
        ):
            if self.current.type == TokenType.AND:
                self.consume()
            right = self._parse_not()
            left = AndNode(left, right)
        return left

    def _parse_not(self) -> Node:
        if self.current.type == TokenType.NOT:
            self.consume()
            operand = self._parse_atom()
            return NotNode(operand)
        return self._parse_atom()

    def _parse_atom(self) -> Node:
        if self.current.type == TokenType.LPAREN:
            self.consume()
            node = self._parse_or()
            self.consume(TokenType.RPAREN)
            return node
        return self._parse_term()

    def _parse_term(self) -> Node:
        tok = self.current
        if tok.type == TokenType.TAG:
            self.consume()
            return _parse_tag_token(tok.value)
        if tok.type == TokenType.WORD:
            self.consume()
            return NamePattern(tok.value)
        raise ParseError(
            f"Unexpected token {tok.type.name} ({tok.value!r}) at position {self.pos}"
        )


def _parse_tag_token(value: str) -> TagPattern:
    colon = value.index(":")
    return TagPattern(prefix=value[:colon], suffix=value[colon + 1 :])


def parse_query(text: str) -> Node | None:
    """Parse a query string and return the AST root (or None for empty queries)."""
    return QueryParser(tokenize(text.strip())).parse()


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------


def _fnmatch(value: str, pattern: str) -> bool:
    return fnmatch.fnmatch(value.lower(), pattern.lower())


def _device_names(device: dict) -> list[str]:
    names = []
    if hostname := device.get("hostname"):
        names.append(hostname)
    if fqdn := device.get("name"):
        names.append(fqdn)
        short = fqdn.split(".")[0]
        if short not in names:
            names.append(short)
    return names


def _device_tags(device: dict) -> list[str]:
    raw = device.get("tags") or []
    return [t[4:] if t.startswith("tag:") else t for t in raw]


def _user_names(user: dict) -> list[str]:
    names = []
    for field in ("loginName", "displayName", "name"):
        if v := user.get(field):
            names.append(v)
    return names


def _user_tags(user: dict) -> list[str]:
    return list(user.get("tags") or [])


def _group_names(group: dict) -> list[str]:
    name = group.get("name", "")
    # groups are like "group:admins"; also match the short name
    return [name, name[6:]] if name.startswith("group:") else [name]


def _match_name_pattern(pattern: NamePattern, names: list[str]) -> bool:
    return any(_fnmatch(n, pattern.pattern) for n in names)


def _match_tag_pattern(pattern: TagPattern, tags: list[str]) -> bool:
    target = pattern.normalized
    return any(_fnmatch(t, target) for t in tags)


def _match_node(node: Node, names: list[str], tags: list[str]) -> bool:
    if isinstance(node, AndNode):
        return _match_node(node.left, names, tags) and _match_node(
            node.right, names, tags
        )
    if isinstance(node, OrNode):
        return _match_node(node.left, names, tags) or _match_node(
            node.right, names, tags
        )
    if isinstance(node, NotNode):
        return not _match_node(node.operand, names, tags)
    if isinstance(node, NamePattern):
        return _match_name_pattern(node, names)
    if isinstance(node, TagPattern):
        return _match_tag_pattern(node, tags)
    raise TypeError(f"Unknown node type: {type(node)}")


def matches_device(node: Node, resource: dict) -> bool:
    return _match_node(node, _device_names(resource), _device_tags(resource))


def matches_user(node: Node, resource: dict) -> bool:
    return _match_node(node, _user_names(resource), _user_tags(resource))


def _match_group_node(node: Node, resource: dict) -> bool:
    """Group-aware node matching that handles 'group:name' colon-form queries."""
    if isinstance(node, AndNode):
        return _match_group_node(node.left, resource) and _match_group_node(node.right, resource)
    if isinstance(node, OrNode):
        return _match_group_node(node.left, resource) or _match_group_node(node.right, resource)
    if isinstance(node, NotNode):
        return not _match_group_node(node.operand, resource)
    if isinstance(node, NamePattern):
        return _match_name_pattern(node, _group_names(resource))
    if isinstance(node, TagPattern):
        # 'group:admins' should match a group whose name is 'group:admins'
        colon_form = f"{node.prefix}:{node.suffix}"
        name = resource.get("name", "")
        if _fnmatch(name, colon_form):
            return True
        # Also match against non-group member entries (tags/users in member list)
        members = resource.get("members", [])
        tags = [m for m in members if not m.startswith("group:")]
        return _match_tag_pattern(node, tags)
    raise TypeError(f"Unknown node type: {type(node)}")


def matches_group(node: Node, resource: dict) -> bool:
    return _match_group_node(node, resource)


def matches_service(node: Node, resource: dict) -> bool:
    names = [
        resource.get("proto", ""),
        resource.get("device", ""),
        f"{resource.get('device', '')}:{resource.get('port', '')}",
    ]
    names = [n for n in names if n]
    return _match_node(node, names, [])


_MATCHERS = {
    "devices": matches_device,
    "users": matches_user,
    "groups": matches_group,
    "services": matches_service,
}


def filter_resources(
    resources: list[dict],
    query: str,
    resource_type: str = "devices",
) -> list[dict]:
    """Filter a list of resources using the query DSL."""
    if not query or not query.strip():
        return resources
    node = parse_query(query)
    if node is None:
        return resources
    matcher = _MATCHERS.get(resource_type, matches_device)
    return [r for r in resources if matcher(node, r)]
