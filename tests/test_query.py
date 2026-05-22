"""Tests for the query DSL: tokeniser, parser, and matching."""

import pytest

from query_ts.query import (
    AndNode,
    NamePattern,
    NotNode,
    OrNode,
    ParseError,
    TagPattern,
    Token,
    TokenType,
    filter_resources,
    matches_device,
    matches_group,
    matches_service,
    matches_user,
    parse_query,
    tokenize,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_empty_string(self):
        tokens = tokenize("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_single_word(self):
        tokens = tokenize("web-prod")
        assert tokens[0] == Token(TokenType.WORD, "web-prod")
        assert tokens[1].type == TokenType.EOF

    def test_glob_word(self):
        tokens = tokenize("web-*")
        assert tokens[0] == Token(TokenType.WORD, "web-*")

    def test_and_keyword_case_insensitive(self):
        for kw in ("AND", "and", "And"):
            tokens = tokenize(kw)
            assert tokens[0].type == TokenType.AND, f"failed for {kw!r}"

    def test_or_keyword_case_insensitive(self):
        for kw in ("OR", "or", "Or"):
            tokens = tokenize(kw)
            assert tokens[0].type == TokenType.OR, f"failed for {kw!r}"

    def test_tag_token(self):
        tokens = tokenize("tag:env-prod")
        assert tokens[0] == Token(TokenType.TAG, "tag:env-prod")

    def test_prefix_colon_suffix(self):
        tokens = tokenize("env:production")
        assert tokens[0] == Token(TokenType.TAG, "env:production")

    def test_not_token_at_start(self):
        tokens = tokenize("-foo")
        assert tokens[0].type == TokenType.NOT
        assert tokens[1] == Token(TokenType.WORD, "foo")

    def test_hyphen_inside_word_not_negation(self):
        tokens = tokenize("my-device")
        assert len(tokens) == 2  # WORD + EOF
        assert tokens[0] == Token(TokenType.WORD, "my-device")

    def test_not_before_paren(self):
        tokens = tokenize("-(foo)")
        assert tokens[0].type == TokenType.NOT
        assert tokens[1].type == TokenType.LPAREN

    def test_parentheses(self):
        tokens = tokenize("(a OR b)")
        types = [t.type for t in tokens]
        assert types == [
            TokenType.LPAREN,
            TokenType.WORD,
            TokenType.OR,
            TokenType.WORD,
            TokenType.RPAREN,
            TokenType.EOF,
        ]

    def test_multiple_words_implicit_and(self):
        tokens = tokenize("foo bar baz")
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert types == [TokenType.WORD, TokenType.WORD, TokenType.WORD]

    def test_tag_with_glob(self):
        tokens = tokenize("env:prod*")
        assert tokens[0] == Token(TokenType.TAG, "env:prod*")

    def test_and_hyphenated_word_not_keyword(self):
        tokens = tokenize("AND-server")
        assert tokens[0] == Token(TokenType.WORD, "AND-server")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParseQuery:
    def test_none_for_empty(self):
        assert parse_query("") is None
        assert parse_query("   ") is None

    def test_single_name_pattern(self):
        node = parse_query("web-*")
        assert node == NamePattern("web-*")

    def test_tag_pattern_tag_prefix(self):
        node = parse_query("tag:env-prod")
        assert isinstance(node, TagPattern)
        assert node.prefix == "tag"
        assert node.suffix == "env-prod"
        assert node.normalized == "env-prod"

    def test_tag_pattern_custom_prefix(self):
        node = parse_query("env:production")
        assert isinstance(node, TagPattern)
        assert node.prefix == "env"
        assert node.suffix == "production"
        assert node.normalized == "env-production"

    def test_implicit_and(self):
        node = parse_query("web env:prod")
        assert isinstance(node, AndNode)
        assert isinstance(node.left, NamePattern)
        assert isinstance(node.right, TagPattern)

    def test_explicit_and(self):
        node = parse_query("web AND env:prod")
        assert isinstance(node, AndNode)

    def test_or(self):
        node = parse_query("web OR api")
        assert isinstance(node, OrNode)
        assert node.left == NamePattern("web")
        assert node.right == NamePattern("api")

    def test_negation(self):
        node = parse_query("-web")
        assert isinstance(node, NotNode)
        assert node.operand == NamePattern("web")

    def test_negation_tag(self):
        node = parse_query("-tag:deprecated")
        assert isinstance(node, NotNode)
        assert isinstance(node.operand, TagPattern)

    def test_or_precedence_over_and(self):
        # a b OR c  =>  (a AND b) OR c  ... but wait, OR has lower precedence
        # Grammar: or_expr := and_expr (OR and_expr)*
        # So "a b OR c" => AndNode(a,b) OR c   -- wrong, let's recheck
        # Actually: "a b OR c" tokens are: WORD WORD OR WORD
        # parse_or() calls parse_and() first, which consumes "a b" (both WORDs joined by implicit AND)
        # Then sees OR, so combines with parse_and() for "c"
        # Result: OrNode(AndNode(a,b), c)
        node = parse_query("a b OR c")
        assert isinstance(node, OrNode)
        assert isinstance(node.left, AndNode)

    def test_parentheses(self):
        node = parse_query("(web OR api) AND env:prod")
        assert isinstance(node, AndNode)
        assert isinstance(node.left, OrNode)
        assert isinstance(node.right, TagPattern)

    def test_complex_nested(self):
        node = parse_query("(web-* OR api-*) env:production -tag:deprecated")
        # ((web-* OR api-*) AND env:production) AND -tag:deprecated
        assert isinstance(node, AndNode)

    def test_parse_error_unmatched_paren(self):
        with pytest.raises(ParseError):
            parse_query("(web OR api")

    def test_parse_error_unexpected_token(self):
        with pytest.raises(ParseError):
            parse_query("OR web")

    def test_multiple_or(self):
        node = parse_query("a OR b OR c")
        # Should be left-associative: (a OR b) OR c
        assert isinstance(node, OrNode)
        assert isinstance(node.left, OrNode)

    def test_not_with_parens(self):
        node = parse_query("-(web OR api)")
        assert isinstance(node, NotNode)
        assert isinstance(node.operand, OrNode)


# ---------------------------------------------------------------------------
# Tag normalization
# ---------------------------------------------------------------------------


class TestTagPattern:
    def test_tag_prefix_normalized(self):
        p = TagPattern(prefix="tag", suffix="env-prod")
        assert p.normalized == "env-prod"

    def test_custom_prefix_normalized(self):
        p = TagPattern(prefix="env", suffix="prod")
        assert p.normalized == "env-prod"

    def test_prefix_only_normalized(self):
        p = TagPattern(prefix="env", suffix="")
        assert p.normalized == "env"


# ---------------------------------------------------------------------------
# Device matching
# ---------------------------------------------------------------------------


class TestMatchDevice:
    def _device(self, hostname, tags=None):
        return {
            "hostname": hostname,
            "name": f"{hostname}.tail1234.ts.net",
            "tags": tags or [],
        }

    def test_name_exact(self):
        d = self._device("web-prod-1")
        assert matches_device(parse_query("web-prod-1"), d)

    def test_name_glob(self):
        d = self._device("web-prod-1")
        assert matches_device(parse_query("web-*"), d)
        assert not matches_device(parse_query("api-*"), d)

    def test_name_fqdn_glob(self):
        d = self._device("web-prod-1")
        assert matches_device(parse_query("web-prod-1.tail*"), d)

    def test_name_case_insensitive(self):
        d = self._device("Web-Prod-1")
        assert matches_device(parse_query("web-prod-1"), d)

    def test_tag_tag_prefix(self):
        d = self._device("x", tags=["tag:env-production"])
        assert matches_device(parse_query("tag:env-production"), d)

    def test_tag_custom_prefix(self):
        d = self._device("x", tags=["tag:env-production"])
        assert matches_device(parse_query("env:production"), d)

    def test_tag_glob(self):
        d = self._device("x", tags=["tag:env-production"])
        assert matches_device(parse_query("env:prod*"), d)
        assert not matches_device(parse_query("env:stag*"), d)

    def test_tag_not_present(self):
        d = self._device("x", tags=["tag:env-staging"])
        assert not matches_device(parse_query("tag:env-production"), d)

    def test_no_tags_does_not_match_tag_query(self):
        d = self._device("x", tags=None)
        assert not matches_device(parse_query("tag:anything"), d)

    def test_implicit_and(self):
        d = self._device("web-prod-1", tags=["tag:env-production"])
        assert matches_device(parse_query("web-* env:production"), d)
        assert not matches_device(parse_query("api-* env:production"), d)

    def test_explicit_and(self):
        d = self._device("web-prod-1", tags=["tag:env-production"])
        assert matches_device(parse_query("web-* AND env:production"), d)

    def test_or(self):
        d1 = self._device("web-prod-1", tags=[])
        d2 = self._device("api-prod-1", tags=[])
        q = parse_query("web-* OR api-*")
        assert matches_device(q, d1)
        assert matches_device(q, d2)
        assert not matches_device(q, self._device("db-prod-1"))

    def test_negation_name(self):
        d = self._device("web-prod-1")
        assert not matches_device(parse_query("-web-*"), d)
        assert matches_device(parse_query("-api-*"), d)

    def test_negation_tag(self):
        d = self._device("x", tags=["tag:env-production"])
        assert not matches_device(parse_query("-env:production"), d)
        assert matches_device(parse_query("-env:staging"), d)

    def test_complex_query(self):
        d = self._device("web-prod-1", tags=["tag:env-production", "tag:role-web"])
        assert matches_device(
            parse_query("(web-* OR api-*) env:production -tag:deprecated"), d
        )

    def test_none_query_always_matches(self):
        d = self._device("anything")
        # filter_resources with empty query returns all
        result = filter_resources([d], "", "devices")
        assert result == [d]


# ---------------------------------------------------------------------------
# filter_resources
# ---------------------------------------------------------------------------


class TestFilterResources:
    def test_empty_query_returns_all(self, devices):
        assert filter_resources(devices, "") == devices

    def test_whitespace_query_returns_all(self, devices):
        assert filter_resources(devices, "   ") == devices

    def test_name_filter(self, devices):
        result = filter_resources(devices, "web-*")
        assert len(result) == 2
        assert all(d["hostname"].startswith("web-") for d in result)

    def test_tag_filter_custom_prefix(self, devices):
        result = filter_resources(devices, "env:production")
        assert len(result) == 3
        assert all("tag:env-production" in (d.get("tags") or []) for d in result)

    def test_tag_filter_tag_prefix(self, devices):
        result = filter_resources(devices, "tag:env-production")
        assert len(result) == 3

    def test_combined_filter(self, devices):
        result = filter_resources(devices, "web-* env:production")
        assert len(result) == 2

    def test_or_filter(self, devices):
        result = filter_resources(devices, "web-* OR api-*")
        assert len(result) == 3

    def test_negation_filter(self, devices):
        result = filter_resources(devices, "-env:production")
        hostnames = {d["hostname"] for d in result}
        assert hostnames == {"api-staging-1", "laptop-alice"}

    def test_complex_filter(self, devices):
        result = filter_resources(devices, "(web-* OR api-*) AND -env:staging")
        hostnames = {d["hostname"] for d in result}
        assert hostnames == {"web-prod-1", "web-prod-2"}

    def test_no_match_returns_empty(self, devices):
        assert filter_resources(devices, "nonexistent-*") == []

    def test_resource_type_users(self, users):
        result = filter_resources(users, "alice*", "users")
        assert len(result) == 1
        assert result[0]["loginName"] == "alice@example.com"

    def test_resource_type_groups(self, groups):
        result = filter_resources(groups, "admins", "groups")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# User matching
# ---------------------------------------------------------------------------


class TestMatchUser:
    def _user(self, login, display=""):
        return {"loginName": login, "displayName": display}

    def test_login_glob(self):
        u = self._user("alice@example.com", "Alice")
        assert matches_user(parse_query("alice*"), u)

    def test_display_name_glob(self):
        u = self._user("alice@example.com", "Alice Admin")
        assert matches_user(parse_query("Alice*"), u)

    def test_no_match(self):
        u = self._user("alice@example.com")
        assert not matches_user(parse_query("bob*"), u)


# ---------------------------------------------------------------------------
# Group matching
# ---------------------------------------------------------------------------


class TestMatchGroup:
    def test_short_name(self):
        g = {"name": "group:admins", "members": []}
        assert matches_group(parse_query("admins"), g)

    def test_full_name(self):
        g = {"name": "group:admins", "members": []}
        assert matches_group(parse_query("group:admins"), g)

    def test_no_match(self):
        g = {"name": "group:devs", "members": []}
        assert not matches_group(parse_query("admins"), g)


# ---------------------------------------------------------------------------
# Service matching
# ---------------------------------------------------------------------------


class TestMatchService:
    def _svc(self):
        return {
            "name": "svc:web",
            "addrs": ["100.93.49.180"],
            "ports": ["tcp:443"],
            "tags": ["tag:env-production"],
        }

    def test_full_name(self):
        assert matches_service(parse_query("svc:web"), self._svc())

    def test_short_name(self):
        assert matches_service(parse_query("web"), self._svc())

    def test_name_glob(self):
        assert matches_service(parse_query("svc:w*"), self._svc())

    def test_address_match(self):
        assert matches_service(parse_query("100.93.49.180"), self._svc())

    def test_tag_match(self):
        assert matches_service(parse_query("tag:env-production"), self._svc())
        assert matches_service(parse_query("env:production"), self._svc())

    def test_no_match(self):
        assert not matches_service(parse_query("db"), self._svc())
