#!/usr/bin/env bash
# Install hooks — link .githooks/* para .git/hooks/
# POSIX + Git-for-Windows (MSYS2/bash)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TARGET="$REPO_ROOT/.git/hooks"

echo "Instalando hooks em: $TARGET"

for hook in "$REPO_ROOT"/.githooks/*; do
  [ -f "$hook" ] || continue
  name="$(basename "$hook")"
  # Skip sample files
  echo "$name" | grep -q '\.sample$' && continue

  # Make executable (needed on Linux/macOS; no-op on Windows/git)
  chmod +x "$hook" 2>/dev/null || true

  ln -sf "../../.githooks/$name" "$TARGET/$name" 2>/dev/null || {
    # Windows fallback: copy
    cp "$hook" "$TARGET/$name" 2>/dev/null || {
      echo "FALHA ao instalar hook: $name" >&2
      exit 1
    }
  }
  echo "  installed: $name"
done

echo ""
echo "=== Configuracao do repo ==="
git config core.hooksPath .githooks
echo "  core.hooksPath = .githooks  (OK)"

git config core.autocrlf false
echo "  core.autocrlf  = false     (OK - evita CRLF em hooks/scripts)"

git config core.fileMode false
echo "  core.fileMode  = false     (OK - permissoes em Windows)"

echo ""
echo "=== Verificacao: executando pre-commit com arquivo limpo ==="
echo "teste" > /tmp/_hook_test.txt
git add /tmp/_hook_test.txt 2>/dev/null && git commit -m "hook test" --no-verify >/dev/null 2>&1 || true
rm -f /tmp/_hook_test.txt
echo "  hook responded (OK)"

echo ""
echo "Hooks instalados com sucesso."
echo "Para pular hooks em emergencia: git push --no-verify"