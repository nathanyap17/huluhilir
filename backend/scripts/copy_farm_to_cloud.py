"""Copy ONE farm -- rows and media -- from the laptop's SQLite into Cloud SQL.

Used once to move the team farm (Kebun MiaoMiao) to the cloud backend with
the SAME ids, so the admin pin (CALENDAR_OWNER_FARM_ID), its restore code and
its whole diagnosis history keep working. Idempotent: rows that already exist
(same primary key) are skipped, so it is safe to re-run.

What is copied: every row of every table that belongs to the farm -- found by
farm_id, or through the farm's blocks / walk sessions / observations / agent
runs. Global tables (treatment rules, knowledge docs, speech templates,
weather cache) are NOT copied: the cloud backend seeds its own.

Usage (Cloud SQL Auth Proxy running locally, see WORKSPACE_SETUP.md):
    python -m scripts.copy_farm_to_cloud \\
        --farm-id 01M2YNGWJ9FGFBB1FP5T4T95YZ \\
        --target-url "postgresql+asyncpg://USER:PASS@127.0.0.1:5432/DBNAME" \\
        [--source-url sqlite+aiosqlite:///./huluhilir.db] [--dry-run]

It then prints the media files to upload and the exact `gcloud storage cp`
command (photos and voice labels live in the huluhilir-media bucket, which
Cloud Run mounts at /media).
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base  # noqa: F401  (registers every model)

MEDIA_BUCKET = "huluhilir-media"


def _insert_ignore(dialect: str, table, rows):
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(table).values(rows).on_conflict_do_nothing()


async def collect(source_url: str, farm_id: str) -> tuple[dict, list[str]]:
    """{table_name: [row dicts]} for this farm, in FK-safe order, + media URIs."""
    engine = create_async_engine(source_url)
    out: dict[str, list[dict]] = {}
    keys: dict[str, set] = {}
    async with engine.connect() as conn:
        farm = (await conn.execute(select(Base.metadata.tables["farms"]).where(
            Base.metadata.tables["farms"].c.farm_id == farm_id))).mappings().first()
        if farm is None:
            raise SystemExit(f"farm {farm_id} not found in {source_url}")
        keys["user_id"] = {farm["user_id"]}
        keys["farm_id"] = {farm_id}

        # Which key ties each table to the farm, in priority order.
        links = [
            ("farm_id", "farm_id"),
            ("walk_session_id", "walk_session_id"),
            ("observation_id", "observation_id"),
            ("run_id", "run_id"),
            ("block_id", "block_id"),
            ("target_block_id", "block_id"),
            ("source_block_id", "block_id"),
        ]
        # Collect in dependency order so ids discovered upstream (blocks, runs,
        # sessions, observations) are known before dependent tables are read.
        order = ["users", "farms", "blocks", "walk_sessions", "diagnosis_cycles", "agent_runs", "observations"]
        tables = [Base.metadata.tables[n] for n in order if n in Base.metadata.tables]
        tables += [t for t in Base.metadata.sorted_tables if t.name not in order]

        for table in tables:
            cols = table.c
            cond = None
            if table.name == "users":
                cond = cols.user_id.in_(keys["user_id"])
            else:
                for col, key in links:
                    if col in cols and keys.get(key):
                        cond = cols[col].in_(keys[key])
                        break
            if cond is None:
                continue  # global table -- the cloud seeds its own
            rows = [dict(r) for r in (await conn.execute(select(table).where(cond))).mappings().all()]
            if not rows:
                continue
            out[table.name] = rows
            ownkey = {"blocks": "block_id", "walk_sessions": "walk_session_id",
                      "observations": "observation_id", "agent_runs": "run_id"}.get(table.name)
            if ownkey:
                keys[ownkey] = {r[ownkey] for r in rows}
        # Global rows this farm's rows point at (treatment rules). Copied too,
        # skipped on insert if the cloud seed already has them.
        tids = {r["treatment_id"] for r in out.get("recommendations", []) if r.get("treatment_id")}
        if tids:
            topt = Base.metadata.tables["treatment_options"]
            out["treatment_options"] = [
                dict(r) for r in (await conn.execute(select(topt).where(topt.c.treatment_id.in_(tids)))).mappings().all()
            ]
    await engine.dispose()

    # Drop rows whose foreign key points at nothing (Postgres would reject the
    # whole copy). Observed: a recommendation for block "block-123", invented
    # by the model before the rules check existed.
    dropped: list[str] = []
    changed = True
    while changed:
        changed = False
        for tname, rows in list(out.items()):
            table = Base.metadata.tables[tname]
            keep = []
            for r in rows:
                bad = None
                for fk in table.foreign_keys:
                    val = r.get(fk.parent.name)
                    parent = fk.column.table.name
                    if val is None or (tname == "farms" and fk.parent.name == "walk_session_id"):
                        continue
                    if parent in out and val not in {p[fk.column.name] for p in out[parent]}:
                        bad = f"{tname}.{fk.parent.name}={val!r} -> no such {parent}"
                        break
                if bad:
                    dropped.append(bad)
                    changed = True
                else:
                    keep.append(r)
            out[tname] = keep
    for d in dropped:
        print(f"  SKIPPED (broken reference) {d}")

    media: list[str] = []
    for r in out.get("blocks", []):
        media += [r.get("photo_uri"), r.get("voice_label_uri")]
    for r in out.get("observations", []):
        media.append(r.get("image_uri"))
    media = sorted({m for m in media if m and m.startswith("/media/")})
    return out, media


async def write(target_url: str, data: dict) -> dict[str, int]:
    """Insert in FK-safe order; returns rows ACTUALLY inserted per table
    (existing primary keys are skipped, so a re-run reports 0)."""
    from sqlalchemy import event, func, update

    engine = create_async_engine(target_url)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        # Behave like Postgres in tests: enforce foreign keys.
        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # farms <-> walk_sessions reference each other (farms.walk_session_id).
    # Postgres enforces FKs, so the farm goes in WITHOUT that link first and
    # gets it back once its walk sessions exist.
    farm_links = {r["farm_id"]: r.get("walk_session_id") for r in data.get("farms", [])}
    order = ["users", "farms", "walk_sessions"]
    tables = [Base.metadata.tables[n] for n in order] + [
        t for t in Base.metadata.sorted_tables if t.name not in order
    ]
    inserted: dict[str, int] = {}
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # new v2 tables, if the cloud has not started yet
        for table in tables:
            rows = data.get(table.name)
            if not rows:
                continue
            if table.name == "farms":
                rows = [{**r, "walk_session_id": None} for r in rows]
            before = (await conn.execute(select(func.count()).select_from(table))).scalar_one()
            for i in range(0, len(rows), 500):
                await conn.execute(_insert_ignore(dialect, table, rows[i:i + 500]))
            after = (await conn.execute(select(func.count()).select_from(table))).scalar_one()
            inserted[table.name] = after - before
        farms = Base.metadata.tables["farms"]
        for fid, wsid in farm_links.items():
            if wsid:
                await conn.execute(update(farms).where(farms.c.farm_id == fid).values(walk_session_id=wsid))
    await engine.dispose()
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--farm-id", required=True)
    ap.add_argument("--target-url", required=True, help="Cloud SQL via the Auth Proxy (postgresql+asyncpg://...)")
    ap.add_argument("--source-url", default="sqlite+aiosqlite:///./huluhilir.db")
    ap.add_argument("--media-dir", default="./media")
    ap.add_argument("--dry-run", action="store_true", help="show what would be copied; write nothing")
    args = ap.parse_args()

    data, media = asyncio.run(collect(args.source_url, args.farm_id))
    print("Rows found for this farm:")
    for name, rows in data.items():
        print(f"  {name:28s} {len(rows)}")

    missing = [m for m in media if not (Path(args.media_dir) / Path(m).name).is_file()]
    print(f"Media files referenced: {len(media)} ({len(missing)} missing locally)")
    for m in missing:
        print(f"  MISSING {m}")

    if args.dry_run:
        print("Dry run -- nothing written.")
        return
    inserted = asyncio.run(write(args.target_url, data))
    print(f"Inserted {sum(inserted.values())} new rows (rows already in the target were skipped):")
    for name, n in inserted.items():
        print(f"  {name:28s} +{n}")

    listfile = Path("media_to_upload.txt")
    present = [str(Path(args.media_dir) / Path(m).name) for m in media if m not in missing]
    listfile.write_text("\n".join(present) + "\n", encoding="utf-8")
    print(f"\nNow upload the media ({len(present)} files) -- run from backend/:")
    print(f"  gcloud storage cp {' '.join(present[:3])}{' ...' if len(present) > 3 else ''} gs://{MEDIA_BUCKET}/")
    print(f"  (full list in {listfile}; or: cat {listfile} | gcloud storage cp -I gs://{MEDIA_BUCKET}/)")


if __name__ == "__main__":
    main()
