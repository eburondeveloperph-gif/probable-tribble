class EburonCodemaxxx < Formula
  desc "CodeMaxxx — AI coding agent for the terminal, powered by Ollama"
  homepage "https://github.com/eburondeveloperph-gif/probable-tribble"
  url "https://github.com/eburondeveloperph-gif/probable-tribble/archive/refs/heads/main.tar.gz"
  version "0.1.0"
  license "MIT"

  depends_on "python@3.14" => :recommended
  depends_on "ollama" => :recommended
  depends_on "postgresql@17" => :optional

  def install
    # Install bash CLI
    bin.install "bin/codemaxxx" => "eburon-codemaxxx"

    # Install zsh bootstrap
    (share/"codemaxxx").install "zsh/eburon_bootstrap.zsh"

    # Install Python source
    libexec.install Dir["src/*"]
    libexec.install "pyproject.toml"
    libexec.install "requirements.txt"
    libexec.install "setup.sh"
    libexec.install "setup_db.sh"

    # Create venv and install Python deps
    venv = libexec/".venv"
    system "python3", "-m", "venv", venv.to_s
    system venv/"bin/pip", "install", "--quiet", "-r", "requirements.txt"
    system venv/"bin/pip", "install", "--quiet", "-e", "."

    # Wrapper that uses the venv Python
    (bin/"eburon-codemaxxx-tui").write <<~EOS
      #!/bin/bash
      exec "#{venv}/bin/python" -m codemaxxx.main "$@"
    EOS
  end

  def caveats
    <<~EOS
      🚀 eburon-codemaxxx installed!

      Commands:
        eburon-codemaxxx                # full bootstrap + launch
        eburon-codemaxxx tui            # TUI agent (alias: eburon-codemaxxx-tui)
        eburon-codemaxxx install        # install Ollama + model + OpenCode
        eburon-codemaxxx launch         # quick launch
        eburon-codemaxxx help           # show help

      To add zsh functions (eburon_bootstrap, eburon_opencode):
        echo 'source "#{share}/codemaxxx/eburon_bootstrap.zsh"' >> ~/.zshrc
    EOS
  end

  test do
    assert_match "codemaxxx", shell_output("#{bin}/eburon-codemaxxx help")
  end
end
