{
  description = "Dev shell (uv + python)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-25.11-darwin";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        python = pkgs.python314;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            uv
            python
            git
            openssl
            pkg-config
            poppler-utils
            jq
          ];

          # Good defaults for uv + venvs in a repo.
          shellHook = ''
            export UV_CACHE_DIR="$PWD/.cache/uv"
            export VIRTUAL_ENV="$PWD/.venv"
            export PATH="$VIRTUAL_ENV/bin:$PATH"

            echo "🔧 devshell: uv=$(uv --version 2>/dev/null || true) python=$(${python}/bin/python --version 2>/dev/null || true)"
            echo "   Tip: uv venv && uv sync"
          '';
        };
      }
    );
}
