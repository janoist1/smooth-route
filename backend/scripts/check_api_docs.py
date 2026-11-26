#!/usr/bin/env python3
"""Check that docs/API_SURFACE.md and schema.graphql match the real GraphQL schema.

The doc lists every root field once, in table rows of the form

    | `fieldName` | <access> | <public: yes|no> | purpose |

and this script compares those rows with the Strawberry schema objects:

- a schema field missing from the doc, or a doc row for a field that no longer
  exists, or a field listed twice;
- an access level that differs from the resolver's permission class
  (anonymous / signed-in / signed-in* / admin; `signed-in*` = anonymous on the
  public read-only deploy);
- a wrong "public" flag (served by the read-only schema or not);
- a stale schema.graphql (repo root; `--write-sdl` regenerates it).

No DB, no torch, under a second:

  cd backend && ../.venv/bin/python scripts/check_api_docs.py
  cd backend && ../.venv/bin/python scripts/check_api_docs.py --write-sdl
"""
import argparse
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
DOC = os.path.join(ROOT, "docs", "API_SURFACE.md")
SDL = os.path.join(ROOT, "schema.graphql")

ACCESS_BY_PERMISSION = {
    (): "anonymous",
    ("IsAuthenticated",): "signed-in",
    ("IsAuthenticatedUnlessPublicRead",): "signed-in*",
    ("IsAdmin",): "admin",
}
ROW_RE = re.compile(r"^\|\s*`(\w+)`\s*\|\s*([\w*-]+)\s*\|\s*(yes|no)\s*\|")


def schema_fields():
    """{field: (access, public)} for every Query and Mutation root field."""
    sys.path.insert(0, BACKEND)
    from app.graphql.limits import PUBLIC_DENIED_ROOT_FIELDS
    from app.graphql.schema import read_schema, schema

    def roots(s):
        for root in ("Query", "Mutation"):
            definition = s.get_type_by_name(root)
            for field in definition.fields if definition else ():
                yield s.config.name_converter.from_field(field), field

    public = {name for name, _ in roots(read_schema)} - set(PUBLIC_DENIED_ROOT_FIELDS)
    fields = {}
    for name, field in roots(schema):
        permissions = tuple(
            p.__name__ if isinstance(p, type) else type(p).__name__
            for p in field.permission_classes
        )
        access = ACCESS_BY_PERMISSION.get(permissions, "+".join(permissions))
        fields[name] = (access, "yes" if name in public else "no")
    return fields, schema


def doc_rows():
    """[(field, access, public)] from the operation tables of the doc."""
    with open(DOC, encoding="utf-8") as f:
        return [m.groups() for m in map(ROW_RE.match, f) if m]


def problems(write_sdl: bool = False) -> list:
    fields, schema = schema_fields()
    rows = doc_rows()
    out = []
    listed = [name for name, _, _ in rows]
    for name in sorted(set(listed)):
        if listed.count(name) > 1:
            out.append(f"{name}: listed {listed.count(name)} times in API_SURFACE.md")
        if name not in fields:
            out.append(f"{name}: in API_SURFACE.md but not in the schema (remove the row)")
    for name, (access, public) in fields.items():
        if name not in listed:
            out.append(f"{name}: missing from API_SURFACE.md (add: | `{name}` | {access} | {public} | … |)")
    for name, access, public in rows:
        if name in fields and (access, public) != fields[name]:
            out.append(f"{name}: doc says {access} / public {public}, "
                       f"schema says {fields[name][0]} / public {fields[name][1]}")

    from strawberry.printer import print_schema

    sdl = print_schema(schema) + "\n"
    if write_sdl:
        with open(SDL, "w", encoding="utf-8") as f:
            f.write(sdl)
    else:
        with open(SDL, encoding="utf-8") as f:
            if f.read() != sdl:
                out.append("schema.graphql is stale (run: scripts/check_api_docs.py --write-sdl)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-sdl", action="store_true", help="regenerate schema.graphql")
    found = problems(parser.parse_args().write_sdl)
    for line in found:
        print(f"FAIL {line}")
    if not found:
        print("OK: API_SURFACE.md and schema.graphql match the GraphQL schema")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
