"""Integration tests for the CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from query_ts.api import TailscaleAPIError
from query_ts.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client(devices, users, groups):
    """Return a context manager mock that simulates TailscaleClient."""
    client = MagicMock()
    client.get_devices.return_value = devices
    client.get_users.return_value = users
    client.get_groups.return_value = groups
    client.get_services.return_value = []
    client.get_acl.return_value = {"groups": {}, "acls": []}

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, client


def invoke(runner, args, env=None):
    env = {"TAILSCALE_API_KEY": "test-key", **(env or {})}
    return runner.invoke(main, args, env=env, catch_exceptions=False)


class TestCLIBasic:
    def test_no_api_key_fails(self, runner):
        result = runner.invoke(main, [], env={})
        assert result.exit_code != 0
        assert "API key" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "QUERY LANGUAGE" in result.output
        assert "--json" in result.output
        assert "--yaml" in result.output
        assert "--plain" in result.output

    def test_short_help(self, runner):
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "query-ts" in result.output


class TestCLIDevices:
    def test_list_all_devices(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color"])
        assert result.exit_code == 0
        assert "web-prod-1" in result.output

    def test_filter_devices_by_name(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color", "web-*"])
        assert result.exit_code == 0
        assert "web-prod-1" in result.output
        assert "api-staging-1" not in result.output

    def test_filter_by_tag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color", "env:production"])
        assert result.exit_code == 0
        assert "web-prod-1" in result.output
        assert "api-staging-1" not in result.output

    def test_filter_negation(self, runner, mock_client, devices):
        # Queries starting with '-' must use -- to prevent Click treating them as flags
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color", "--", "-env:production"])
        assert result.exit_code == 0
        assert "api-staging-1" in result.output
        assert "web-prod-1" not in result.output

    def test_no_results(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color", "nonexistent-*"])
        assert result.exit_code == 0
        assert "no results" in result.output


class TestCLIOutputFormats:
    def test_json_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-j"])
        assert result.exit_code == 0
        import json
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_json_long_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--json"])
        assert result.exit_code == 0
        import json
        parsed = json.loads(result.output)
        assert len(parsed) == len(devices)

    def test_yaml_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-y"])
        assert result.exit_code == 0
        import yaml
        parsed = yaml.safe_load(result.output)
        assert isinstance(parsed, list)

    def test_plain_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-p"])
        assert result.exit_code == 0
        assert "web-prod-1" in result.output
        # No rich table elements
        assert "╭" not in result.output

    def test_format_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-f", "json"])
        assert result.exit_code == 0
        import json
        assert isinstance(json.loads(result.output), list)

    def test_invalid_format_flag(self, runner, mock_client):
        cm, _ = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-f", "xml"])
        assert result.exit_code != 0

    def test_comma_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-p", "-c"])
        assert result.exit_code == 0
        assert "," in result.output
        assert "\n" not in result.output.rstrip()

    def test_separator_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-p", "-s", " | "])
        assert result.exit_code == 0
        assert " | " in result.output

    def test_field_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-p", "--field", "user"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output


class TestCLIResourceTypes:
    def test_users_flag(self, runner, mock_client, users):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--users", "--no-color"])
        assert result.exit_code == 0
        client.get_users.assert_called_once()
        assert "alice@example.com" in result.output

    def test_groups_flag(self, runner, mock_client, groups):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--groups", "--no-color"])
        assert result.exit_code == 0
        client.get_groups.assert_called_once()
        assert "group:admins" in result.output

    def test_services_flag(self, runner, mock_client):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--services", "--no-color"])
        assert result.exit_code == 0
        client.get_services.assert_called_once()

    def test_acl_flag(self, runner, mock_client):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--acl", "--no-color"])
        assert result.exit_code == 0
        client.get_acl.assert_called_once()

    def test_type_flag(self, runner, mock_client, users):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["-t", "users", "--no-color"])
        assert result.exit_code == 0
        client.get_users.assert_called_once()

    def test_type_flag_overrides_boolean(self, runner, mock_client, users):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--devices", "-t", "users", "--no-color"])
        assert result.exit_code == 0
        client.get_users.assert_called_once()
        client.get_devices.assert_not_called()


class TestCLIAuth:
    def test_api_key_from_env(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm) as mock_cls:
            result = invoke(runner, ["--no-color"], env={"TAILSCALE_API_KEY": "my-key"})
        assert result.exit_code == 0
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["api_key"] == "my-key"

    def test_api_key_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm) as mock_cls:
            result = runner.invoke(
                main, ["-k", "flag-key", "--no-color"], catch_exceptions=False
            )
        assert result.exit_code == 0
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["api_key"] == "flag-key"

    def test_tailnet_flag(self, runner, mock_client, devices):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm) as mock_cls:
            result = invoke(runner, ["-n", "my-tailnet.com", "--no-color"])
        assert result.exit_code == 0
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["tailnet"] == "my-tailnet.com"


class TestCLIErrors:
    def test_api_error_shown(self, runner):
        cm = MagicMock()
        cm.__enter__ = MagicMock(
            side_effect=TailscaleAPIError(401, "Unauthorized")
        )
        cm.__exit__ = MagicMock(return_value=False)
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color"])
        assert result.exit_code != 0
        assert "Unauthorized" in result.output

    def test_bad_query_shown(self, runner, mock_client):
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            result = invoke(runner, ["--no-color", "OR missing"])
        assert result.exit_code != 0
        assert "parse error" in result.output.lower()

    def test_double_dash_passes_query(self, runner, mock_client, devices):
        """-- allows passing a query that starts with a dash (negation) literally."""
        cm, client = mock_client
        with patch("query_ts.cli.TailscaleClient", return_value=cm):
            # -web-* is a valid NOT query even without --
            result = invoke(runner, ["--no-color", "--", "-web-*"])
        assert result.exit_code == 0
        # negation: web-* excluded
        assert "web-prod-1" not in result.output
        assert "api-staging-1" in result.output
