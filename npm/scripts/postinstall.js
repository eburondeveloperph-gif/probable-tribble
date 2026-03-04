#!/usr/bin/env node
// postinstall — clone repo + set up Python venv + optional runtime bootstrap

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const INSTALL_DIR = path.join(os.homedir(), ".codemaxxx");
const REPO = "https://github.com/eburondeveloperph-gif/probable-tribble.git";
const AUTO_INSTALL_ENABLED =
  !["0", "false", "no", "off"].includes(String(process.env.CODEMAXXX_AUTO_INSTALL || "").toLowerCase());

function run(cmd) {
  try {
    execSync(cmd, { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function runVerbose(cmd) {
  try {
    execSync(cmd, { stdio: "inherit" });
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

const cliPath = path.join(INSTALL_DIR, "bin", "codemax");
if (AUTO_INSTALL_ENABLED && fs.existsSync(cliPath)) {
  console.log("  → Auto-installing Ollama + model + OpenCode (set CODEMAXXX_AUTO_INSTALL=0 to skip)...");
  const ok = runVerbose(`bash "${cliPath}" install`);
  if (!ok) {
    console.log("  ⚠ Auto-install step failed (non-fatal).");
    console.log("    Run manually: codemax install");
  }
}

const npmBin = (() => {
  try {
    return execSync("npm bin -g", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "";
  }
})();

if (npmBin) {
  const pathParts = (process.env.PATH || "").split(path.delimiter);
  if (!pathParts.includes(npmBin)) {
    console.log(`  ⚠ npm global bin is not in PATH: ${npmBin}`);
    console.log(`    Add it, then reload shell: export PATH="${npmBin}:$PATH"`);
  }
}

console.log("");
console.log("  ✅ Installed! Run:");
console.log("     codemax                    # launch TUI agent");
console.log("     codemax install            # install Ollama + model + OpenCode");
console.log("     codemax help               # show all commands");
console.log("     eburon-codemaxxx           # compatibility alias");
console.log("");
