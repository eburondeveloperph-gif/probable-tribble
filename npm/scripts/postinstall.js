#!/usr/bin/env node
// postinstall — clone repo + set up Python venv silently

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const INSTALL_DIR = path.join(os.homedir(), ".codemaxxx");
const REPO = "https://github.com/eburondeveloperph-gif/probable-tribble.git";

function run(cmd) {
  try {
    execSync(cmd, { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

console.log("");
console.log("  🚀 eburon-codemaxxx — postinstall");
console.log("  ──────────────────────────────────");

// Clone repo
if (!fs.existsSync(path.join(INSTALL_DIR, ".git"))) {
  console.log("  → Cloning CodeMaxxx...");
  run(`git clone --quiet "${REPO}" "${INSTALL_DIR}"`);
} else {
  console.log("  → Updating CodeMaxxx...");
  run(`git -C "${INSTALL_DIR}" pull --quiet`);
}

// Set up Python venv
const venvPython = path.join(INSTALL_DIR, ".venv", "bin", "python");
if (!fs.existsSync(venvPython)) {
  console.log("  → Setting up Python environment...");
  run(`python3 -m venv "${path.join(INSTALL_DIR, ".venv")}"`);
}

const pip = path.join(INSTALL_DIR, ".venv", "bin", "pip");
if (fs.existsSync(pip)) {
  console.log("  → Installing Python dependencies...");
  run(`"${pip}" install --quiet -e "${INSTALL_DIR}"`);
}

console.log("");
console.log("  ✅ Installed! Run:");
console.log("     codemax                    # launch TUI agent");
console.log("     codemax install            # install Ollama + model + OpenCode");
console.log("     codemax help               # show all commands");
console.log("     eburon-codemaxxx           # compatibility alias");
console.log("");
