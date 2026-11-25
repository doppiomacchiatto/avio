#!/usr/bin/env node
// Builds the GitHub release body from RELEASE-NOTES-v<version>-beta.md (used by .github/workflows/release.yml).
//   node scripts/release-notes.mjs <version> <out-file> <installer>...
// - takes everything below the first line that is exactly "---" (the draft checklist above it is for the
//   developer, never published)
// - puts each installer's real SHA-256 into its row of the hash table ("| `<file name>` | `<hash>` |"), so the
//   published hashes are always those of the files attached to the release, whatever the committed notes say
//   (write PENDING in the table when the notes are drafted before the CI build)
// - fails if an installer has no row, or the notes still contain PENDING
// Prints the release title (the first "# " heading of the body) on stdout.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const [version, outFile, ...installers] = process.argv.slice(2);
if (!version || !outFile || !installers.length) {
  console.error("usage: node scripts/release-notes.mjs <version> <out-file> <installer>...");
  process.exit(2);
}
const notesPath = path.resolve(`RELEASE-NOTES-v${version}-beta.md`);
if (!fs.existsSync(notesPath)) { console.error(`missing ${path.basename(notesPath)}`); process.exit(1); }

const lines = fs.readFileSync(notesPath, "utf8").split(/\r?\n/);
const sep = lines.findIndex((l) => l.trim() === "---");
let body = (sep >= 0 ? lines.slice(sep + 1) : lines).join("\n").trim() + "\n";

for (const file of installers) {
  if (!fs.existsSync(file)) { console.error(`not found: ${file}`); process.exit(1); }
  const name = path.basename(file);
  const hash = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex").toUpperCase();
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const row = new RegExp("^(\\|\\s*`" + esc + "`\\s*\\|\\s*`)([0-9A-Fa-f]{64}|PENDING)(`\\s*\\|)", "m");
  if (!row.test(body)) { console.error(`no hash row for ${name} in ${path.basename(notesPath)}`); process.exit(1); }
  body = body.replace(row, `$1${hash}$3`);
  console.error(`${name}  ${hash}`);
}
if (/PENDING/.test(body)) { console.error("the notes still contain PENDING"); process.exit(1); }

fs.writeFileSync(outFile, body);
const title = (body.match(/^# (.+)$/m) || [])[1] || `Avio ${version} Beta`;
console.log(title.trim());
