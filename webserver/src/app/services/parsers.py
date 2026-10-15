from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


PARSER_VERSIONS = {
    "simple_list": "simple_asset_list_v1",
    "subfinder": "subfinder_jsonl_v1",
    "dnsx": "dnsx_jsonl_v1",
    "httpx": "projectdiscovery_httpx_jsonl_v1",
    "nuclei": "projectdiscovery_nuclei_jsonl_v1",
    "greyartifact_observations": "greyartifact_observations_v1",
}

# Property codes a normalized observation line may set; they must match the
# property types seeded by the migrations.
OBSERVATION_PROPERTIES = frozenset(
    {
        "http_status",
        "title",
        "server",
        "content_type",
        "tls_subject_cn",
        "tls_issuer_cn",
        "tls_not_before",
        "tls_not_after",
        "source_value",
    }
)
OBSERVATION_RELATIONSHIPS = frozenset({"resolves_to", "hosts"})


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


@dataclass(frozen=True)
class ParsedFinding:
    asset: ParsedAsset | None
    source: str
    external_id: str
    title: str
    description: str | None
    severity: str
    matcher_name: str
    matched_at: str
    metadata: dict[str, object]
    is_sensitive: bool
    line: int


@dataclass
class ParsedReport:
    assets: dict[tuple[str, str], ParsedAsset] = field(default_factory=dict)
    properties: list[ParsedProperty] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)
    findings: list[ParsedFinding] = field(default_factory=list)
    _finding_keys: set[tuple[str, str, str]] = field(default_factory=set)

    def add_asset(self, asset: ParsedAsset) -> ParsedAsset:
        return self.assets.setdefault((asset.type_code, asset.canonical_value), asset)

    def add_finding(self, finding: ParsedFinding) -> None:
        key = (finding.external_id, finding.matcher_name, finding.matched_at)
        if key not in self._finding_keys:
            self._finding_keys.add(key)
            self.findings.append(finding)


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


def _observation_asset(type_code: object, value: object) -> ParsedAsset:
    if type_code == "domain":
        return domain_asset(value)
    if type_code in {"ipv4", "ipv6"}:
        asset = ip_asset(value)
        if asset.type_code != type_code:
            raise ParserError(f"value is not {type_code}")
        return asset
    if type_code == "url":
        return url_asset(value)
    if type_code == "service_endpoint":
        if not isinstance(value, str):
            raise ParserError("service_endpoint must be a string")
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ParserError("service_endpoint must be an HTTP(S) origin")
        host = parsed.hostname.lower().rstrip(".")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        host_repr = f"[{host}]" if ":" in host else host
        canonical = f"{parsed.scheme.lower()}://{host_repr}:{port}"
        return ParsedAsset("service_endpoint", canonical, value.strip())
    raise ParserError(f"unsupported asset type: {type_code!r}")


def _parse_observation(line: int, obj: dict, report: "ParsedReport") -> None:
    asset_obj = obj.get("asset")
    if not isinstance(asset_obj, dict):
        raise ParserError("asset must be an object")
    asset = report.add_asset(_observation_asset(asset_obj.get("type"), asset_obj.get("value")))
    properties = obj.get("properties", {})
    if not isinstance(properties, dict):
        raise ParserError("properties must be an object")
    for code, value in properties.items():
        if code not in OBSERVATION_PROPERTIES:
            raise ParserError(f"unsupported property: {code}")
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            raise ParserError(f"property {code} must not be a boolean")
        report.properties.append(ParsedProperty(asset, code, str(value), line))
    relationships = obj.get("relationships", [])
    if not isinstance(relationships, list):
        raise ParserError("relationships must be an array")
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise ParserError("relationship must be an object")
        code = relationship.get("type")
        if code not in OBSERVATION_RELATIONSHIPS:
            raise ParserError(f"unsupported relationship: {code}")
        target_obj = relationship.get("target")
        if not isinstance(target_obj, dict):
            raise ParserError("relationship target must be an object")
        target = report.add_asset(
            _observation_asset(target_obj.get("type"), target_obj.get("value"))
        )
        report.relationships.append(ParsedRelationship(asset, code, target, line))


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


def _string(value: object, field_name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ParserError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise ParserError(f"{field_name} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise ParserError(f"{field_name} is required")
    return cleaned or None


def _string_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ParserError(f"{field_name} must be a string or an array of strings")
    return [item.strip() for item in value if item.strip()]


def _nuclei_asset(matched_at: str, host_value: object) -> ParsedAsset | None:
    candidates = [matched_at]
    if isinstance(host_value, str) and host_value.strip() not in candidates:
        candidates.append(host_value.strip())
    for candidate in candidates:
        try:
            parsed_asset = url_asset(candidate)
            parsed_url = urlsplit(parsed_asset.canonical_value)
            safe_url = urlunsplit(
                (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "")
            )
            return ParsedAsset("url", safe_url, safe_url)
        except ParserError:
            pass
        try:
            parsed_host = urlsplit(f"//{candidate}").hostname
        except ValueError:
            parsed_host = None
        if not parsed_host:
            continue
        try:
            return ip_asset(parsed_host)
        except ParserError:
            try:
                return domain_asset(parsed_host)
            except ParserError:
                continue
    return None


def _parse_nuclei_finding(line: int, obj: dict) -> ParsedFinding:
    external_id = _string(
        obj.get("template-id", obj.get("templateID")),
        "template-id",
        required=True,
    )
    matched_at = _string(
        obj.get("matched-at", obj.get("host")),
        "matched-at",
        required=True,
    )
    info = obj.get("info") or {}
    if not isinstance(info, dict):
        raise ParserError("info must be an object")
    title = _string(info.get("name"), "info.name") or external_id
    description = _string(info.get("description"), "info.description")
    severity = str(info.get("severity", "unknown")).strip().lower()
    if severity not in {"info", "low", "medium", "high", "critical", "unknown"}:
        severity = "unknown"
    matcher_name = _string(obj.get("matcher-name"), "matcher-name") or ""
    tags = _string_list(info.get("tags"), "info.tags")
    references = _string_list(
        info.get("reference", info.get("references")),
        "info.reference",
    )
    classification = info.get("classification") or {}
    if not isinstance(classification, dict):
        raise ParserError("info.classification must be an object")
    safe_classification = {
        key: classification[key]
        for key in ("cve-id", "cwe-id", "cvss-score", "cvss-metrics")
        if key in classification
    }
    metadata: dict[str, object] = {}
    if tags:
        metadata["tags"] = tags
    if references:
        metadata["references"] = references
    if safe_classification:
        metadata["classification"] = safe_classification
    sensitive_markers = ("secret", "token", "credential", "api-key", "apikey")
    sensitive_values = [external_id.lower(), *(tag.lower() for tag in tags)]
    is_sensitive = any(
        marker in value for marker in sensitive_markers for value in sensitive_values
    )
    asset = _nuclei_asset(matched_at, obj.get("host"))
    safe_matched_at = (
        asset.canonical_value if asset is not None and asset.type_code == "url" else matched_at
    )
    return ParsedFinding(
        asset=asset,
        source="nuclei",
        external_id=external_id,
        title=title,
        description=description,
        severity=severity,
        matcher_name=matcher_name,
        matched_at=safe_matched_at,
        metadata=metadata,
        is_sensitive=is_sensitive,
        line=line,
    )


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
            elif tool_name == "httpx":
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
            elif tool_name == "greyartifact_observations":
                _parse_observation(line, obj, report)
            else:
                finding = _parse_nuclei_finding(line, obj)
                if finding.asset is not None:
                    report.add_asset(finding.asset)
                report.add_finding(finding)
        except ParserError as exc:
            if str(exc).startswith("line "):
                raise
            raise ParserError(f"line {line}: {exc}") from exc
    return report


def parse_asset_list(chunks) -> ParsedReport:
    report = ParsedReport()
    for line, raw in _json_lines(chunks):
        try:
            value = raw.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ParserError(f"line {line}: input is not valid UTF-8") from exc
        if not value or value.startswith("#"):
            continue
        try:
            if value.lower().startswith(("http://", "https://")):
                asset = url_asset(value)
            else:
                try:
                    asset = ip_asset(value)
                except ParserError:
                    asset = domain_asset(value)
        except ParserError as exc:
            raise ParserError(f"line {line}: unsupported asset value") from exc
        asset = report.add_asset(asset)
        report.properties.append(ParsedProperty(asset, "source_value", value, line))
    if not report.assets:
        raise ParserError("asset list contains no values")
    return report


def parse_report(parser_name: str, chunks) -> ParsedReport:
    if parser_name == "simple_list":
        return parse_asset_list(chunks)
    return parse_jsonl(parser_name, chunks)
