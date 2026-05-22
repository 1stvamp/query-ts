"""Tests for output formatters."""

import json

import pytest
import yaml

from query_ts.formatter import (
    JsonFormatter,
    PlainFormatter,
    TableFormatter,
    YamlFormatter,
    make_formatter,
)


class TestJsonFormatter:
    def test_devices(self, devices):
        output = JsonFormatter().format(devices, "devices")
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == len(devices)

    def test_empty(self):
        output = JsonFormatter().format([], "devices")
        assert json.loads(output) == []

    def test_pretty_printed(self, devices):
        output = JsonFormatter(indent=4).format(devices[:1], "devices")
        # should have indentation
        assert "    " in output

    def test_non_serializable_handled(self):
        from datetime import datetime
        data = [{"ts": datetime(2024, 1, 1)}]
        output = JsonFormatter().format(data, "devices")
        assert "2024" in output


class TestYamlFormatter:
    def test_devices(self, devices):
        output = YamlFormatter().format(devices, "devices")
        parsed = yaml.safe_load(output)
        assert isinstance(parsed, list)
        assert len(parsed) == len(devices)

    def test_empty(self):
        output = YamlFormatter().format([], "devices")
        parsed = yaml.safe_load(output)
        assert parsed == []

    def test_output_is_string(self, devices):
        assert isinstance(YamlFormatter().format(devices, "devices"), str)


class TestPlainFormatter:
    def test_default_newline_separator(self, devices):
        output = PlainFormatter().format(devices, "devices")
        lines = output.split("\n")
        assert len(lines) == len(devices)

    def test_hostnames_used_for_devices(self, devices):
        output = PlainFormatter().format(devices, "devices")
        assert "web-prod-1" in output
        assert "api-staging-1" in output

    def test_comma_separator(self, devices):
        output = PlainFormatter(separator=",").format(devices, "devices")
        assert "\n" not in output
        assert "," in output

    def test_custom_separator(self, devices):
        output = PlainFormatter(separator=" | ").format(devices, "devices")
        assert " | " in output

    def test_custom_field(self, devices):
        output = PlainFormatter(field="user").format(devices, "devices")
        assert "alice@example.com" in output

    def test_empty_returns_empty_string(self):
        assert PlainFormatter().format([], "devices") == ""

    def test_users_login_name(self, users):
        output = PlainFormatter().format(users, "users")
        assert "alice@example.com" in output
        assert "bob@example.com" in output

    def test_single_device(self, devices):
        output = PlainFormatter().format(devices[:1], "devices")
        assert output == "web-prod-1"


class TestTableFormatter:
    def test_devices_produces_output(self, devices):
        output = TableFormatter(color=False).format(devices, "devices")
        assert "web-prod-1" in output

    def test_online_indicator(self, devices):
        output = TableFormatter(color=False).format(devices, "devices")
        # online / offline indicators
        assert "●" in output or "○" in output

    def test_tags_shown(self, devices):
        output = TableFormatter(color=False).format(devices, "devices")
        assert "env-production" in output

    def test_empty_shows_no_results(self):
        output = TableFormatter(color=False).format([], "devices")
        assert output == "(no results)"

    def test_users_format(self, users):
        output = TableFormatter(color=False).format(users, "users")
        assert "alice@example.com" in output
        assert "admin" in output

    def test_groups_format(self, groups):
        output = TableFormatter(color=False).format(groups, "groups")
        assert "group:admins" in output

    def test_services_format(self, services):
        output = TableFormatter(color=False).format(services, "services")
        assert "svc:web" in output
        assert "tcp:443" in output
        assert "100.93.49.180" in output
        # tags are shown with the "tag:" prefix stripped
        assert "env-production" in output
        assert "tag:env-production" not in output

    def test_acl_format(self):
        # cli._fetch flattens the ACL into name/value items
        acl_items = [
            {"name": "acls", "value": [{"action": "accept"}]},
            {"name": "tagOwners", "value": {"tag:prod": ["group:admins"]}},
        ]
        output = TableFormatter(color=False).format(acl_items, "acl")
        # The ACL keys appear in the Key column...
        assert "acls" in output
        assert "tagOwners" in output
        # ...and the literal "name"/"value" dict keys do not leak into output.
        rows = [line for line in output.splitlines() if "│" in line]
        key_cells = [line.split("│")[1].strip() for line in rows]
        assert "name" not in key_cells
        assert "value" not in key_cells

    def test_tags_strip_tag_prefix(self, devices):
        output = TableFormatter(color=False).format(devices[:1], "devices")
        # "tag:env-production" should appear as "env-production"
        assert "tag:env-production" not in output
        assert "env-production" in output

    def test_returns_string(self, devices):
        assert isinstance(TableFormatter(color=False).format(devices, "devices"), str)


class TestMakeFormatter:
    def test_json(self):
        assert isinstance(make_formatter("json"), JsonFormatter)

    def test_yaml(self):
        assert isinstance(make_formatter("yaml"), YamlFormatter)

    def test_plain(self):
        assert isinstance(make_formatter("plain"), PlainFormatter)

    def test_table(self):
        assert isinstance(make_formatter("table"), TableFormatter)

    def test_default_is_table(self):
        assert isinstance(make_formatter("unknown"), TableFormatter)

    def test_plain_separator_passed(self):
        f = make_formatter("plain", separator=",")
        assert isinstance(f, PlainFormatter)
        assert f.separator == ","

    def test_plain_field_passed(self):
        f = make_formatter("plain", field="id")
        assert isinstance(f, PlainFormatter)
        assert f.field == "id"

    def test_table_color_passed(self):
        f = make_formatter("table", color=False)
        assert isinstance(f, TableFormatter)
        assert f.color is False
