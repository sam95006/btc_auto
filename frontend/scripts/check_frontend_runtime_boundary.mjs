import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const deploymentFiles = [
  resolve(root, "deploy/zeabur_member_preview/Dockerfile"),
  resolve(root, "deploy/zeabur_member_preview_v18_2_1/server.py"),
];
const forbidden = [
  /ResearchAutonomyService/i,
  /\[NEXUS-AUTONOMY\]/i,
  /runtime supervisor/i,
  /shadow worker/i,
  /execution worker/i,
  /backend\/.*start\.sh/i,
  /unified .*app\.py/i,
  /unified .*run\.py/i,
];

for (const file of deploymentFiles) {
  const content = readFileSync(file, "utf8");
  for (const pattern of forbidden) {
    if (pattern.test(content)) {
      throw new Error(`frontend_deployment_boundary_violation:${file}:${pattern}`);
    }
  }
}

const dockerfile = readFileSync(deploymentFiles[0], "utf8");
if (!/COPY --from=build\s+\/build\/frontend\/dist\s+\/app\/dist/.test(dockerfile)
  || !/CMD \["python", "\/app\/server\.py"\]/.test(dockerfile)) {
  throw new Error("frontend_deployment_boundary_missing_static_runtime");
}

console.log("FRONTEND_RUNTIME_BOUNDARY_PASS");
