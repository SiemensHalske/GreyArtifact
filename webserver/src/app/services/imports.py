from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    Asset,
    AssetPropertyObservation,
    AssetRelationshipObservation,
    AssetType,
    Finding,
    ImportRecord,
    ProjectAsset,
    PropertyType,
    RelationshipType,
)
from app.services.artifact_storage import get_artifact_storage
from app.services.parsers import PARSER_VERSIONS, ParsedAsset, ParserError, parse_report


class ImportConfigurationError(RuntimeError):
    pass


def _asset_type(code: str) -> AssetType:
    value = db.session.execute(
        select(AssetType).where(AssetType.code == code)
    ).scalar_one_or_none()
    if value is None:
        raise ImportConfigurationError(f"Missing asset type: {code}")
    return value


def _get_or_create_asset(parsed: ParsedAsset) -> Asset:
    type_value = _asset_type(parsed.type_code)
    asset = db.session.execute(
        select(Asset).where(
            Asset.asset_type_id == type_value.asset_type_id,
            Asset.canonical_value == parsed.canonical_value,
        )
    ).scalar_one_or_none()
    if asset is None:
        asset = Asset(
            asset_id=uuid4(),
            asset_type_id=type_value.asset_type_id,
            canonical_value=parsed.canonical_value,
            display_value=parsed.display_value,
        )
        db.session.add(asset)
        db.session.flush()
    return asset


def process_import(import_id: UUID) -> ImportRecord:
    import_record = db.session.execute(
        select(ImportRecord).where(ImportRecord.import_id == import_id).with_for_update()
    ).scalar_one()
    if import_record.status == "completed":
        return import_record
    parser_name = PARSER_VERSIONS.get(import_record.parser_name or "")
    if parser_name is None:
        raise ParserError("unsupported report tool")

    from app.models import Artifact

    artifact = db.session.get(Artifact, import_record.artifact_id)
    storage = get_artifact_storage()
    try:
        report = parse_report(
            import_record.parser_name,
            storage.iter_bytes(artifact.storage_key),
        )
        db.session.execute(
            delete(AssetPropertyObservation).where(
                AssetPropertyObservation.import_id == import_record.import_id
            )
        )
        db.session.execute(
            delete(AssetRelationshipObservation).where(
                AssetRelationshipObservation.import_id == import_record.import_id
            )
        )
        db.session.execute(
            delete(Finding).where(Finding.import_id == import_record.import_id)
        )
        mapped_assets = {
            key: _get_or_create_asset(parsed) for key, parsed in report.assets.items()
        }
        for asset in mapped_assets.values():
            if db.session.get(ProjectAsset, (import_record.project_id, asset.asset_id)) is None:
                db.session.add(
                    ProjectAsset(project_id=import_record.project_id, asset_id=asset.asset_id)
                )
        property_types = {
            item.code: item
            for item in db.session.execute(select(PropertyType)).scalars().all()
        }
        relationship_types = {
            item.code: item
            for item in db.session.execute(select(RelationshipType)).scalars().all()
        }
        for observation in report.properties:
            property_type = property_types.get(observation.code)
            if property_type is None:
                raise ImportConfigurationError(
                    f"Missing property type: {observation.code}"
                )
            asset = mapped_assets[(observation.asset.type_code, observation.asset.canonical_value)]
            db.session.add(
                AssetPropertyObservation(
                    observation_id=uuid4(),
                    import_id=import_record.import_id,
                    asset_id=asset.asset_id,
                    property_type_id=property_type.property_type_id,
                    value_text=observation.value,
                    evidence_locator=f"line:{observation.line}",
                )
            )
        for observation in report.relationships:
            relationship_type = relationship_types.get(observation.code)
            if relationship_type is None:
                raise ImportConfigurationError(
                    f"Missing relationship type: {observation.code}"
                )
            source = mapped_assets[
                (observation.source.type_code, observation.source.canonical_value)
            ]
            target = mapped_assets[
                (observation.target.type_code, observation.target.canonical_value)
            ]
            db.session.add(
                AssetRelationshipObservation(
                    observation_id=uuid4(),
                    import_id=import_record.import_id,
                    source_asset_id=source.asset_id,
                    relationship_type_id=relationship_type.relationship_type_id,
                    target_asset_id=target.asset_id,
                    evidence_locator=f"line:{observation.line}",
                )
            )
        for parsed_finding in report.findings:
            asset = None
            if parsed_finding.asset is not None:
                asset = mapped_assets[
                    (
                        parsed_finding.asset.type_code,
                        parsed_finding.asset.canonical_value,
                    )
                ]
            db.session.add(
                Finding(
                    finding_id=uuid4(),
                    project_id=import_record.project_id,
                    import_id=import_record.import_id,
                    asset_id=asset.asset_id if asset else None,
                    source=parsed_finding.source,
                    external_id=parsed_finding.external_id,
                    title=parsed_finding.title,
                    description=parsed_finding.description,
                    severity=parsed_finding.severity,
                    status="new",
                    matcher_name=parsed_finding.matcher_name,
                    matched_at=parsed_finding.matched_at,
                    metadata_json=parsed_finding.metadata,
                    is_sensitive=parsed_finding.is_sensitive,
                    evidence_locator=f"line:{parsed_finding.line}",
                )
            )
        import_record.parser_version = parser_name
        import_record.status = "completed"
        import_record.error_message = None
        db.session.commit()
        return import_record
    except (ParserError, ImportConfigurationError) as exc:
        db.session.rollback()
        failed = db.session.get(ImportRecord, import_id)
        failed.parser_version = parser_name
        failed.status = "failed"
        failed.error_message = str(exc)[:2000]
        db.session.commit()
        raise
