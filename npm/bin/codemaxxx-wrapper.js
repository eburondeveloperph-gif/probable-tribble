#!/usr/bin/env node
// codemax / eburon-codemaxxx — npm wrapper that bootstraps and launches CodeMaxxx

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const INSTALL_DIR = path.join(os.homedir(), ".codemaxxx");
const REPO = "https://github.com/eburondeveloperph-gif/probable-tribble.git";
const VENV_PYTHON = path.join(INSTALL_DIR, ".venv", "bin", "python");
const BASH_CLI = path.join(INSTALL_DIR, "bin", "codemax");
const BASH_CLI_COMPAT = path.join(INSTALL_DIR, "bin", "codemaxxx");

function run(cmd, opts = {}) {
  try {
    return execSync(cmd, { stdio: "inherit", ...opts });
  } catch {
    return null;
  }
}

function ensureRepo() {
  if (fs.existsSync(path.join(INSTALL_DIR, ".git"))) {
    run(`git -C "${INSTALL_DIR}" pull --quiet`);
  } else {
    run(`git clone --quiet "${REPO}" "${INSTALL_DIR}"`);
  }
}

function ensureVenv() {
  if (!fs.existsSync(VENV_PYTHON)) {
    run(`python3 -m venv "${path.join(INSTALL_DIR, ".venv")}"`);
  }
  run(`"${path.join(INSTALL_DIR, ".venv", "bin", "pip")}" install --quiet -e "${INSTALL_DIR}"`);
}

// Pass-through args
const args = process.argv.slice(2);
const cmd = args[0] || "";

// If "tui" or no args → launch Python TUI
if (cmd === "tui" || cmd === "") {
  ensureRepo();
  ensureVenv();

  if (fs.existsSync(VENV_PYTHON)) {
    const child = spawn(VENV_PYTHON, ["-m", "codemaxxx.main", ...args.slice(cmd === "tui" ? 1 : 0)], {
      stdio: "inherit",
      cwd: process.cwd(),
    });
    child.on("exit", (code) => process.exit(code || 0));
  } else {
    console.error("❌ Python venv not found. Run: codemax install");
    process.exit(1);
  }
} else {
  // Delegate to bash CLI for install/launch/pull/help
  ensureRepo();
  const cliPath = fs.existsSync(BASH_CLI) ? BASH_CLI : BASH_CLI_COMPAT;
  if (fs.existsSync(cliPath)) {
    const child = spawn("bash", [cliPath, ...args], {
      stdio: "inherit",
      cwd: process.cwd(),
    });
    child.on("exit", (code) => process.exit(code || 0));
  } else {
    console.error("❌ CLI not found. Try reinstalling: npm i -g eburon-codemaxxx");
    process.exit(1);
  }
}
