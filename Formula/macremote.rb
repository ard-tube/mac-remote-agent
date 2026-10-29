class Macremote < Formula
  desc "Terminal-first controller and local dashboard for MacRemote"
  homepage "https://github.com/ard-tube/mac-remote-agent"
  url "https://github.com/ard-tube/mac-remote-agent/releases/download/v0.2.0-preview.2/MacRemote-CLI.tar"
  version "0.2.0-preview.2"
  sha256 "3718d582e761983feed07b8c4c933c99878eac6a29f40dc38653908525fdcf65"

  depends_on "python@3.12"
  depends_on "qrencode"

  def install
    libexec.install "agent.py", "macremote.py"
    libexec.install "dashboard"
    (bin/"macremote").write <<~SH
      #!/bin/sh
      exec "#{libexec}/macremote.py" "$@"
    SH
    (bin/"macremote").chmod 0755
  end

  test do
    assert_match "MacRemote terminal-first host controller", shell_output("#{bin}/macremote --help")
  end
end
