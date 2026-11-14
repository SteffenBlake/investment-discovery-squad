"""Central LadybugDB research graph. Claims never substitute for numerical qualification."""

import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .configuration import private_directory, reject_secrets, write_private_json
from .util import canonical, digest, instant, now_utc, stamp

SCHEMA_VERSION = "1"
TABLES = {
    "Metadata": "key STRING PRIMARY KEY, value STRING",
    "Entity": "id STRING PRIMARY KEY, kind STRING, label STRING, symbol STRING, record STRING",
    "Source": "id STRING PRIMARY KEY, url STRING, ingested_at STRING, record STRING",
    "Claim": "id STRING PRIMARY KEY, text STRING, status STRING, confidence DOUBLE, ingested_at STRING, record STRING",
    "Batch": "id STRING PRIMARY KEY, hash STRING, ingested_at STRING, record STRING",
}
KINDS = {"asset", "company", "sector", "event", "region", "indicator", "commodity", "other"}
STATUSES = {"hypothesis", "observed", "supported", "disputed", "invalidated"}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:_.@/-]{0,199}", value):
        raise ValueError("Knowledge IDs must be nonempty stable identifiers (max 200 characters)")
    return value


def text(value, label, maximum=100_000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Invalid {label}: need nonempty text within {maximum} characters")
    return value


class Knowledge:
    def __init__(self, settings, identity, *, create=False, clock=now_utc):
        import ladybug
        self.settings, self.identity, self.clock = settings, identity, clock
        self.path = Path(settings["storage"]["knowledge_path"])
        self.sources = self.path.parent / "knowledge-sources"
        existed = self.path.exists()
        if not existed and not create:
            raise ValueError("Knowledge graph missing; restore its original identity or explicitly initialize it")
        if not existed:
            private_directory(self.path.parent)
        previous = os.umask(0o077)
        try:
            # Auto-sized export parallelism can exhaust this bounded pool on large-CPU hosts.
            self.db = ladybug.Database(str(self.path), buffer_pool_size=128 * 1024 * 1024, max_num_threads=2)
        finally:
            os.umask(previous)
        self.conn = ladybug.Connection(self.db)
        try:
            if not existed:
                for table, fields in TABLES.items():
                    self.conn.execute(f"CREATE NODE TABLE {table}({fields})")
                for statement in (
                    "CREATE REL TABLE About(FROM Claim TO Entity)",
                    "CREATE REL TABLE SupportedBy(FROM Claim TO Source)",
                    "CREATE REL TABLE Contradicts(FROM Claim TO Claim)",
                    "CREATE REL TABLE Related(FROM Entity TO Entity, id STRING, claim_id STRING, record STRING)",
                ):
                    self.conn.execute(statement)
                for key, value in {"schema_version": SCHEMA_VERSION, "profile_id": settings["profile_id"],
                                   "setup_identity": identity, "search_dirty": "true", "revision": digest([])}.items():
                    self.meta(key, value)
            expected = {"schema_version": SCHEMA_VERSION, "profile_id": settings["profile_id"], "setup_identity": identity}
            for key, value in expected.items():
                if self.meta(key) != value:
                    raise ValueError("Knowledge graph ownership/schema mismatch: " + key)
            try:
                self.conn.execute("LOAD EXTENSION fts")
            except RuntimeError:
                if not create:
                    raise ValueError("FTS runtime extension unavailable; run setup-runtime for this pinned Ladybug version") from None
                self.conn.execute("INSTALL fts")
                self.conn.execute("LOAD EXTENSION fts")
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.conn.close()
        self.db.close()

    def rows(self, query, parameters=None):
        result = self.conn.execute(query, parameters or {})
        rows = []
        try:
            while result.has_next():
                rows.append(result.get_next())
        finally:
            result.close()
        return rows

    def meta(self, key, value=None):
        if value is None:
            rows = self.rows("MATCH (m:Metadata) WHERE m.key=$key RETURN m.value", {"key": key})
            return rows[0][0] if rows else None
        self.conn.execute("MERGE (m:Metadata {key:$key}) SET m.value=$value", {"key": key, "value": str(value)})

    def get(self, table, key):
        if table not in TABLES or table == "Metadata":
            raise ValueError("Unsupported knowledge record type")
        rows = self.rows(f"MATCH (n:{table}) WHERE n.id=$id RETURN n.record", {"id": key})
        return json.loads(rows[0][0]) if rows else None

    def status(self):
        counts = {table.lower(): self.rows(f"MATCH (n:{table}) RETURN count(n)")[0][0]
                  for table in TABLES if table != "Metadata"}
        counts["relationships"] = self.rows("MATCH ()-[r:Related]->() RETURN count(r)")[0][0]
        return {"backend": "ladybug", "schema_version": SCHEMA_VERSION, "profile_id": self.settings["profile_id"],
                "setup_identity": self.identity, "knowledge_path": str(self.path), "counts": counts}

    def fingerprint(self):
        records = {table: self.rows(f"MATCH (n:{table}) RETURN n.id, n.record ORDER BY n.id")
                   for table in TABLES if table != "Metadata"}
        records["Related"] = self.rows("MATCH ()-[r:Related]->() RETURN r.id, r.record ORDER BY r.id")
        for table in ('Source', 'Claim', 'Batch'):
            records[table + '_capture_times'] = self.rows(f"MATCH (n:{table}) RETURN n.id, n.ingested_at ORDER BY n.id")
        for relation in ('About', 'SupportedBy', 'Contradicts'):
            records[relation] = self.rows(f"MATCH (a)-[:{relation}]->(b) RETURN a.id, b.id ORDER BY a.id, b.id")
        return digest(records)

    def _validate(self, batch):
        reject_secrets(batch)
        if set(batch) - {"schema_version", "id", "synthetic", "entities", "sources", "claims", "relationships"}:
            raise ValueError("Unknown knowledge batch fields")
        if batch.get("schema_version") != 1 or batch.get("synthetic") is True:
            raise ValueError("Require real research batch schema 1; synthetic investment evidence prohibited")
        identifier(batch.get("id"))
        groups = {key: batch.get(key, []) for key in ("entities", "sources", "claims", "relationships")}
        for key, records in groups.items():
            if not isinstance(records, list) or len(records) > 500:
                raise ValueError("Knowledge batch lists must contain at most 500 records each")
            ids = [identifier(record.get("id")) for record in records]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate knowledge IDs within " + key)
        for entity in groups["entities"]:
            if entity.get("kind") not in KINDS:
                raise ValueError("Unsupported entity kind")
            text(entity.get("label"), "entity label", 1000)
            if "symbol" in entity:
                text(entity["symbol"], "symbol", 100)
        for source in groups["sources"]:
            uri = urlsplit(text(source.get("url"), "source URL", 4000))
            if uri.scheme not in {"https", "http"} or not uri.hostname or uri.username or uri.password:
                raise ValueError("Source needs an HTTP(S) provenance URL without embedded credentials")
            if any(re.search(r'token|secret|password|credential|api.?key|signature', key, re.I) for key, _ in parse_qsl(uri.query)):
                raise ValueError('Source URL must be public provenance, without credential query parameters')
            text(source.get("content"), "original source content", 5_000_000)
            text(source.get("title"), "source title", 2000)
            if source.get("published_at") and instant(source["published_at"]) > instant(self.clock()):
                raise ValueError("Source publication cannot be in the future")
            actual = hashlib.sha256(source["content"].encode()).hexdigest()
            if source.get("content_sha256", actual) != actual:
                raise ValueError("Source content checksum mismatch")
        for claim in groups["claims"]:
            text(claim.get("text"), "claim text")
            if claim.get("status") not in STATUSES:
                raise ValueError("Require explicit claim status; a research claim is not a qualified signal")
            confidence = claim.get("confidence")
            if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Claim confidence must be between 0 and 1")
            for key in ("entity_ids", "source_ids", "contradicts"):
                values = claim.get(key, [])
                if not isinstance(values, list) or len(values) > 100:
                    raise ValueError("Claim references need bounded ID lists")
                for value in values:
                    identifier(value)
            if not claim.get("entity_ids") or not claim.get("source_ids"):
                raise ValueError("Claims require connected entities and original sources")
            for key in ("valid_from", "valid_to"):
                if claim.get(key):
                    instant(claim[key])
            if claim.get("valid_from") and claim.get("valid_to") and instant(claim["valid_from"]) > instant(claim["valid_to"]):
                raise ValueError("Claim validity interval reversed")
        incoming = {"Entity": {r["id"] for r in groups["entities"]}, "Source": {r["id"] for r in groups["sources"]},
                    "Claim": {r["id"] for r in groups["claims"]}}
        def reference(table, key):
            identifier(key)
            if key not in incoming[table] and self.get(table, key) is None:
                raise ValueError("Missing knowledge reference: " + table + "/" + key)
        for claim in groups["claims"]:
            for table, key in (("Entity", "entity_ids"), ("Source", "source_ids"), ("Claim", "contradicts")):
                for value in claim.get(key, []):
                    reference(table, value)
        for relation in groups["relationships"]:
            text(relation.get("kind"), "relationship kind", 100)
            reference("Entity", relation.get("from"))
            reference("Entity", relation.get("to"))
            reference("Claim", relation.get("claim_id"))
        return groups

    def ingest(self, batch):
        groups = self._validate(batch)
        old = self.rows("MATCH (b:Batch) WHERE b.id=$id RETURN b.hash", {"id": batch["id"]})
        if old:
            if old[0][0] != digest(batch):
                raise ValueError("Batch ID reused with different evidence")
            for source in groups['sources']:
                write_private_json(self.sources / (digest(source) + '.json'), source)
            self.ensure_index()
            return {"created": False, "batch_id": batch["id"], "fingerprint": self.meta("revision")}
        self.conn.execute("BEGIN TRANSACTION")
        try:
            at = stamp(self.clock())
            for table, key in (("Entity", "entities"), ("Source", "sources"), ("Claim", "claims")):
                for item in groups[key]:
                    previous = self.get(table, item["id"])
                    if previous is not None:
                        if previous != item:
                            raise ValueError("Immutable knowledge ID reused: " + item["id"])
                        continue
                    params = {"id": item["id"], "record": canonical(item)}
                    fields = "id:$id, record:$record"
                    extras = {"Entity": {"kind": item.get("kind"), "label": item.get("label"), "symbol": item.get("symbol", "")},
                              "Source": {"url": item.get("url"), "ingested_at": at},
                              "Claim": {"text": item.get("text"), "status": item.get("status"), "confidence": item.get("confidence"), "ingested_at": at}}[table]
                    for field, value in extras.items():
                        params[field] = value
                        fields += f", {field}:${field}"
                    self.conn.execute(f"CREATE (n:{table} {{{fields}}})", params)
            for claim in groups["claims"]:
                for relation, table, key in (("About", "Entity", "entity_ids"), ("SupportedBy", "Source", "source_ids"), ("Contradicts", "Claim", "contradicts")):
                    for target in claim.get(key, []):
                        self.conn.execute(f"MATCH (c:Claim), (n:{table}) WHERE c.id=$id AND n.id=$target MERGE (c)-[:{relation}]->(n)",
                                          {"id": claim["id"], "target": target})
            for relation in groups["relationships"]:
                old = self.rows("MATCH ()-[r:Related]->() WHERE r.id=$id RETURN r.record", {"id": relation["id"]})
                if old:
                    if old[0][0] != canonical(relation):
                        raise ValueError("Immutable relationship ID reused")
                    continue
                self.conn.execute("MATCH (a:Entity), (b:Entity) WHERE a.id=$a AND b.id=$b CREATE (a)-[:Related {id:$id, claim_id:$claim, record:$record}]->(b)",
                                  {"a": relation["from"], "b": relation["to"], "id": relation["id"], "claim": relation["claim_id"], "record": canonical(relation)})
            self.conn.execute("CREATE (:Batch {id:$id, hash:$hash, ingested_at:$at, record:$record})",
                              {"id": batch["id"], "hash": digest(batch), "at": at, "record": canonical(batch)})
            self.meta("search_dirty", "true")
            self.meta("revision", digest([self.meta("revision"), digest(batch)]))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        # Original content also lives as portable, content-addressed private artifacts.
        for source in groups["sources"]:
            write_private_json(self.sources / (digest(source) + ".json"), source)
        self.ensure_index()
        return {"created": True, "batch_id": batch["id"], "fingerprint": self.meta("revision"), "counts": self.status()["counts"]}

    def ensure_index(self):
        if self.meta("search_dirty") != "true":
            return
        indexes = self.rows("CALL SHOW_INDEXES() RETURN *")
        if any(row[1] == "claim_text" for row in indexes):
            self.conn.execute("CALL DROP_FTS_INDEX('Claim', 'claim_text')")
        if self.rows("MATCH (c:Claim) RETURN count(c)")[0][0]:
            self.conn.execute("CALL CREATE_FTS_INDEX('Claim', 'claim_text', ['text'])")
        self.meta("search_dirty", "false")

    def claim_packet(self, key):
        claim = self.get("Claim", key)
        if claim is None:
            raise ValueError("Unknown claim: " + key)
        sources = []
        for source_id in claim["source_ids"]:
            source = self.get("Source", source_id)
            captured = self.rows("MATCH (s:Source) WHERE s.id=$id RETURN s.ingested_at", {"id": source_id})[0][0]
            sources.append({"id": source_id, "url": source["url"], "title": source["title"], "published_at": source.get("published_at"),
                            "first_captured_at": captured, "content_sha256": hashlib.sha256(source["content"].encode()).hexdigest(),
                            "excerpt": source["content"][:1200], "content_truncated": len(source["content"]) > 1200})
        contradictory = self.rows("MATCH (a:Claim)-[:Contradicts]-(b:Claim) WHERE a.id=$id RETURN DISTINCT b.record LIMIT 101", {"id": key})
        return {"claim": claim, "entities": [self.get("Entity", i) for i in claim["entity_ids"]], "sources": sources,
                "contradictions": [json.loads(row[0]) for row in contradictory[:100]], "contradictions_truncated": len(contradictory) > 100,
                "qualification": "Research evidence only; historical/live qualification comes from the numerical ledger"}

    def search(self, query, *, limit=10):
        text(query, "search query", 1000)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Search limit must be 1..50")
        self.ensure_index()
        rows = [] if not self.rows('MATCH (c:Claim) RETURN count(c)')[0][0] else self.rows(
            "CALL QUERY_FTS_INDEX('Claim', 'claim_text', $query, top := $limit) RETURN node.id, score ORDER BY score DESC", {"query": query, "limit": limit + 1})
        return {"query": query, "results": [{"score": row[1], **self.claim_packet(row[0])} for row in rows[:limit]],
                "truncated": len(rows) > limit, "limit": limit, "search": "Ranked word matching over saved research claims"}

    def context(self, symbols, *, query=None, limit=15, hops=2):
        if not isinstance(symbols, list) or not symbols or len(symbols) > 100 or any(not isinstance(s, str) for s in symbols):
            raise ValueError("Need 1..100 holding symbols")
        if type(limit) is not int or not 1 <= limit <= 50 or hops not in (1, 2, 3):
            raise ValueError("Context limit 1..50 and hops 1..3 required")
        symbols = list(dict.fromkeys(symbols))
        found = self.rows("MATCH (e:Entity) WHERE e.symbol IN $symbols RETURN e.id, e.symbol LIMIT 101", {"symbols": symbols})
        ids = [row[0] for row in found[:100]]
        neighbours = self.rows(f"MATCH (a:Entity)-[:Related*1..{hops}]-(b:Entity) WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT 201", {"ids": ids}) if ids else []
        connected = list(dict.fromkeys(ids + [r[0] for r in neighbours[:200]]))
        claims = self.rows("MATCH (c:Claim)-[:About]->(e:Entity) WHERE e.id IN $ids RETURN DISTINCT c.id, c.ingested_at ORDER BY c.ingested_at DESC, c.id LIMIT $limit",
                           {"ids": connected, "limit": limit + 1}) if connected else []
        selected = [r[0] for r in claims[:limit]]
        edges = self.rows("""MATCH (a:Entity)-[r:Related]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids
          RETURN r.record ORDER BY r.id LIMIT $limit""", {"ids": connected, "limit": limit + 1}) if connected else []
        relationships = []
        for row in edges[:limit]:
            edge = json.loads(row[0])
            relationships.append({**edge, "direction": "from_to", "support": self.claim_packet(edge["claim_id"])})
        text_result = None
        if query:
            text_result = self.search(query, limit=limit)
        return {"symbols": symbols, "missing_symbols": [s for s in symbols if s not in {r[1] for r in found}],
                "related_entities": [self.get("Entity", key) for key in connected],
                "relationships": relationships, "relationships_truncated": len(edges) > limit,
                "claims": [self.claim_packet(key) for key in selected],
                "text_matches": text_result,
                "truncated": len(found) > 100 or len(neighbours) > 200 or len(claims) > limit or len(edges) > limit,
                "hops": hops, "limit": limit, "fingerprint": self.meta("revision"),
                "instruction": "LLM decides actions using provenance, dates, contradictions and numerical signal status; missing knowledge is not proof of safety"}

    def export(self, destination):
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError("Graph export destination must be new")
        self.ensure_index()
        self.conn.execute("EXPORT DATABASE " + json.dumps(str(destination)))
        return self.fingerprint()

    def import_export(self, source):
        if any(self.status()["counts"].values()):
            raise ValueError("Import requires a newly initialized empty graph")
        # IMPORT requires no schema, including Metadata, in the new database.
        for relation in ("About", "SupportedBy", "Contradicts", "Related"):
            self.conn.execute(f"DROP TABLE {relation}")
        for table in reversed(TABLES):
            self.conn.execute(f"DROP TABLE {table}")
        self.conn.execute("IMPORT DATABASE " + json.dumps(str(Path(source).resolve())))
        for key, value in {"profile_id": self.settings["profile_id"], "setup_identity": self.identity, "schema_version": SCHEMA_VERSION}.items():
            if self.meta(key) != value:
                raise ValueError("Imported graph identity/schema mismatch")
        self.ensure_index()
