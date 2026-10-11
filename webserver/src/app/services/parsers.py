from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


PARSER_VERSIONS = {
    "subfinder": "subfinder_jsonl_v1",
    "dnsx": "dnsx_jsonl_v1",
    "httpx": "projectdiscovery_httpx_jsonl_v1",
}


class ParserError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedAsset:
    type_code: str
    canonical_value: str
    display_value: str


@dataclass(frozen=True)
class ParsedProperty:
    asset: ParsedAsset
    code: str
    value: str
    line: int


@dataclass(frozen=True)
class ParsedRelationship:
    source: ParsedAsset
    code: str
    target: ParsedAsset
    line: int


@dataclass
class ParsedReport:
    assets: dict[tuple[str, str], ParsedAsset] = field(default_factory=dict)
    properties: list[ParsedProperty] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)

    def add_asset(self, asset: ParsedAsset) -> ParsedAsset:
        return self.assets.setdefault((asset.type_code, asset.canonical_value), asset)


def canonical_domain(value: object) -> str:
    if not isinstance(value, str):
        raise ParserError("domain value must be a string")
    candidate = value.strip().rstrip(".").lower()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ParserError("domain value is an IP address")
    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ParserError("domain value is not valid IDNA") from exc
    labels = ascii_domain.split(".")
    if (
        len(ascii_domain) > 253
        or len(labels) < 2
        or any(not label or len(label) > 63 for label in labels)
        or any(label.startswith("-") or label.endswith("-") for label in labels)
        or any(not all(char.isalnum() or char == "-" for char in label) for label in labels)
    ):
        raise ParserError("domain value is invalid")
    return ascii_domain


def domain_asset(value: object) -> ParsedAsset:
    canonical = canonical_domain(value)
    return ParsedAsset("domain", canonical, str(value).strip())


def ip_asset(value: object) -> ParsedAsset:
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ParserError("IP address is invalid") from exc
    code = "ipv4" if address.version == 4 else "ipv6"
    return ParsedAsset(code, address.compressed, address.compressed)


def url_asset(value: object) -> ParsedAsset:
    if not isinstance(value, str):
        raise ParserError("URL must be a string")
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ParserError("URL is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise ParserError("URL must use HTTP or HTTPS")
    host = host.lower().rstrip(".")
    default_port = 80 if parsed.scheme.lower() == "http" else 443
    port_suffix = "" if port in {None, default_port} else f":{port}"
    netloc = f"[{host}]{port_suffix}" if ":" in host else f"{host}{port_suffix}"
    canonical = urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
    )
    return ParsedAsset("url", canonical, value.strip())


def _json_lines(chunks):
    buffer = b""
    line_number = 0
    for chunk in chunks:
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            line_number += 1
            yield line_number, raw
    if buffer:
        line_number += 1
        yield line_number, buffer


def _objects(chunks):
    for line_number, raw in _json_lines(chunks):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParserError(f"line {line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise ParserError(f"line {line_number}: expected a JSON object")
        yield line_number, value


def parse_jsonl(tool_name: str, chunks) -> ParsedReport:
    parser_name = PARSER_VERSIONS.get(tool_name)
    if parser_name is None:
        raise ParserError("unsupported report tool")
    report = ParsedReport()
    for line, obj in _objects(chunks):
        try:
            if tool_name == "subfinder":
                report.add_asset(domain_asset(obj.get("host")))
            elif tool_name == "dnsx":
                host = report.add_asset(domain_asset(obj.get("host")))
                ipv4_values = obj.get("a", []) or []
                ipv6_values = obj.get("aaaa", []) or []
                if not isinstance(ipv4_values, list) or not isinstance(
                    ipv6_values, list
                ):
                    raise ParserError("a and aaaa must be arrays")
                for value in [*ipv4_values, *ipv6_values]:
                    address = report.add_asset(ip_asset(value))
                    report.relationships.append(
                        ParsedRelationship(host, "resolves_to", address, line)
                    )
            else:
                url = report.add_asset(url_asset(obj.get("url")))
                parsed_url = urlsplit(url.canonical_value)
                host_value = parsed_url.hostname
                try:
                    host = report.add_asset(ip_asset(host_value))
                except ParserError:
                    host = report.add_asset(domain_asset(host_value))
                port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
                endpoint = report.add_asset(
                    ParsedAsset(
                        "service_endpoint",
                        f"{parsed_url.scheme}://{host.canonical_value}:{port}",
                        f"{host.display_value}:{port}",
                    )
                )
                report.relationships.append(
                    ParsedRelationship(host, "hosts", url, line)
                )
                report.relationships.append(
                    ParsedRelationship(host, "hosts", endpoint, line)
                )
                http_addresses = obj.get("a", []) or []
                if not isinstance(http_addresses, list):
                    raise ParserError("a must be an array")
                for value in http_addresses:
                    address = report.add_asset(ip_asset(value))
                    if host.type_code == "domain":
                        report.relationships.append(
                            ParsedRelationship(host, "resolves_to", address, line)
                        )
                property_values = {
                    "http_status": obj.get("status_code"),
                    "title": obj.get("title"),
                    "server": obj.get("webserver") or obj.get("server"),
                    "content_type": obj.get("content_type"),
                }
                tls = obj.get("tls") or {}
                if not isinstance(tls, dict):
                    raise ParserError("tls must be an object")
                property_values.update(
                    {
                        "tls_subject_cn": tls.get("subject_cn") or tls.get("subject_dn"),
                        "tls_issuer_cn": tls.get("issuer_cn") or tls.get("issuer_dn"),
                        "tls_not_before": tls.get("not_before"),
                        "tls_not_after": tls.get("not_after"),
                    }
                )
                for code, value in property_values.items():
                    if value is not None and value != "":
                        report.properties.append(
                            ParsedProperty(url, code, str(value), line)
                        )
        except ParserError as exc:
            if str(exc).startswith("line "):
                raise
            raise ParserError(f"line {line}: {exc}") from exc
    return report
