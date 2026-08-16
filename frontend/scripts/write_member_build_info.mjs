import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

function gitSha() {
  for (const value of [
    process.env.ZEABUR_GIT_COMMIT_SHA,
    process.env.GITHUB_SHA,
    process.env.VITE_BUILD_COMMIT,
  ]) {
    if (/^[0-9a-f]{7,40}$/i.test(value || "")) return value;
  }
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: resolve(import.meta.dirname, "../.."),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "local";
  }
}

const sha = gitSha();
const marker = `NEXUS_MEMBER_UI_DATA_TRUTH_${sha.slice(0, 12)}`;
const output = resolve(import.meta.dirname, "../public/build-info.json");
mkdirSync(resolve(output, ".."), { recursive: true });
writeFileSync(output, `${JSON.stringify({
  product: "NEXUS_MEMBER_UI_DATA_TRUTH",
  marker,
  git_sha: sha,
  built_at: new Date().toISOString(),
}, null, 2)}\n`);
console.log(`FRONTEND_BUILD_IDENTITY_PASS ${marker}`);
