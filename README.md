# Build Your Own Git

A Git implementation from scratch, in Python — no `GitPython`, no `subprocess` calls to real `git`, no shortcuts. Every plumbing command reads and writes the actual `.git` object format by hand: SHA-1 hashing, zlib compression, tree/commit parsing, and — for the clone stage — a real implementation of Git's Smart HTTP transfer protocol, including binary pack file parsing and delta (diff) decompression.

Built as part of [Codecrafters' "Build Your Own Git" challenge](https://codecrafters.io/challenges/git), then extended and revised beyond the original scope.

## What's implemented

| Command | What it does |
|---|---|
| `init` | Sets up `.git/objects`, `.git/refs/heads`, and `.git/HEAD` |
| `cat-file -p / -t / -s` | Reads and decompresses any object; prints its content, type, or size |
| `hash-object -w` | Hashes a file as a git blob, optionally writing it to the object store |
| `ls-tree --name-only` | Parses and lists a tree object's entries |
| `write-tree` | Recursively snapshots a directory into tree objects (treats the whole working directory as staged — see *Simplifications* below) |
| `commit-tree` | Builds a commit object with real author/committer timestamps and timezone offsets |
| `clone <url> <dir>` | Clones a public GitHub repo: ref discovery, pack negotiation, binary pack parsing, delta resolution, and checkout |

## How it works

Every git object — blob, tree, or commit — follows the same pattern: `<type> <size>\0<content>`, SHA-1 hashed, zlib compressed, and stored at `.git/objects/<first 2 hex chars>/<remaining 38 chars>` (a sharding trick so no single directory ends up with tens of thousands of files). Because objects are identified by the hash of their own content, identical content anywhere in the repo — a file, a subtree, whatever — is automatically deduplicated and reused, and the smallest edit produces a completely different hash.

**Trees** mix plain text (mode, filename) with raw binary data (a 20-byte SHA-1, not the usual 40-character hex string) in the same entry — parsing this correctly means walking byte-by-byte rather than splitting on a delimiter, since the binary hash bytes can't be assumed safe to split on.

**Clone** was the real deep end. A rough map of what it does:
1. **Ref discovery** — a GET request to `info/refs?service=git-upload-pack`, parsed out of Git's `pkt-line` wire format (every "line" is prefixed with its own byte length instead of relying on a delimiter).
2. **Pack negotiation** — a POST request saying `want <sha>`, requesting everything reachable from the target commit.
3. **Pack parsing** — the response is a binary `PACK` file: a 12-byte header (magic bytes, version, object count) followed by objects with variable-length headers that use a continuation-bit encoding to pack type + size into as few bytes as possible.
4. **Delta resolution** — many objects in a real pack aren't stored in full; they're stored as a diff (a stream of copy/insert instructions) against another object earlier in the same file, referenced by a backward byte offset (`OFS_DELTA`). Reconstructing these means resolving base objects first, then replaying the copy/insert instructions against them.
5. **Checkout** — walking the cloned commit's tree recursively and writing real files to disk, the mirror image of `write-tree`.

## Simplifications (and why)

Being upfront about where this diverges from real git, and why:

- **No staging area.** `write-tree` treats the entire working directory as staged, rather than implementing `.git/index`. Real git separates "what changed" from "what you intend to commit next" — this project skips that layer to keep the focus on the object model itself.
- **`REF_DELTA` objects are detected but not resolved.** Pack files can reference a delta's base object either by a backward byte offset (`OFS_DELTA` — implemented) or by its full SHA-1 hash (`REF_DELTA` — not implemented). `REF_DELTA` shows up in some real-world repos and is currently skipped, meaning a handful of objects can go unwritten on repos that use it heavily. `OFS_DELTA`, which is what most packs primarily use, is fully implemented, including the base-offset math and the copy/insert instruction decoding.
- **No partial/shallow clone, no branch selection.** Clones the default branch only, in full.

## Running it locally

```sh
./your_program.sh init
./your_program.sh hash-object -w somefile.txt
./your_program.sh cat-file -p <sha>
./your_program.sh clone https://github.com/<user>/<repo> <target-dir>
```

Run these from a scratch directory, not this repo's own root — the point of this project is to build and stomp on a *toy* `.git` folder, not this one.
