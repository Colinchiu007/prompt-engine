#!/usr/bin/env node

/**
 * Install the prompt-engine Agent Skill into local AI tools.
 * Usage: node bin/install.mjs
 *
 * Detects the running agent (Claude Code, Cursor, Hermes) and installs
 * the SKILL.md to the appropriate directory.
 */

import { execSync } from "child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_SOURCE = join(__dirname, "..");
const SKILL_NAME = "prompt-engine";

function getTargetPaths() {
  const home = process.env.HOME || process.env.USERPROFILE || "";
  const paths = [];

  // Claude Code
  const claudeCode = join(home, ".claude", "skills");
  if (existsSync(claudeCode)) paths.push(claudeCode);

  // Hermes Agent
  const hermes = join(home, ".hermes", "skills");
  if (existsSync(hermes)) paths.push(hermes);

  // Cursor
  const cursor = join(home, ".cursor", "skills");
  if (existsSync(cursor)) paths.push(cursor);

  return paths;
}

function installSkill(targetDir) {
  const dest = join(targetDir, SKILL_NAME);
  if (!existsSync(dest)) {
    mkdirSync(dest, { recursive: true });
  }

  // Copy SKILL.md
  copyFileSync(join(SKILL_SOURCE, "SKILL.md"), join(dest, "SKILL.md"));
  console.log(`  ✓ SKILL.md → ${join(dest, "SKILL.md")}`);

  // Copy references
  const refsSrc = join(SKILL_SOURCE, "references");
  const refsDest = join(dest, "references");
  if (existsSync(refsSrc)) {
    if (!existsSync(refsDest)) mkdirSync(refsDest, { recursive: true });
    for (const file of readdirSync(refsSrc)) {
      copyFileSync(join(refsSrc, file), join(refsDest, file));
    }
    console.log(`  ✓ references/ → ${refsDest}`);
  }
}

function main() {
  const targets = getTargetPaths();
  if (targets.length === 0) {
    console.log(`No supported AI tool detected.

To install manually:
  cp -r ${SKILL_SOURCE} ~/.claude/skills/${SKILL_NAME}
  cp -r ${SKILL_SOURCE} ~/.hermes/skills/${SKILL_NAME}
  cp -r ${SKILL_SOURCE} ~/.cursor/skills/${SKILL_NAME}`);
    process.exit(1);
  }

  console.log(`Installing ${SKILL_NAME} skill...`);
  for (const target of targets) {
    console.log(`\nTarget: ${target}`);
    installSkill(target);
  }
  console.log(`\n✅ ${SKILL_NAME} skill installed successfully.`);
  console.log(`Run \`prompt-engine --help\` to verify.`);
}

main();
