class Macremote < Formula
  desc "Terminal-first controller and local dashboard for MacRemote"
  homepage "https://github.com/ard-tube/mac-remote-agent"
  url "https://github.com/ard-tube/mac-remote-agent/releases/download/v0.2.0-preview.1/MacRemote-CLI.tar"
  version "0.2.0-preview.1"
  sha256 "a8f5806a09531566ed05379356be88381bf28a87980f8b39f88ed7b05e2843a0"

  depends_on "python@3.12"
  depends_on "qrencode"

  def install
    libexec.install "agent.py", "macremote.py"
    libexec.install "dashboard"
    bin.write_exec_script libexec/"macremote.py"
  end

  test do
    assert_match "MacRemote terminal-first host controller", shell_output("#{bin}/macremote --help")
  end
end
