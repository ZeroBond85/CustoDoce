# WSL Environment - CustoDoce
> Última revisão: 2026-08-14 21:58 UTC

## Configuração Validada (2026-08-14)

### Python 3.14.6 Nativo
- Local: `/usr/local/bin/python3.14` (compilado de tarball oficial)
- Symlinks: `~/bin/python` → `~/bin/python3` → `/usr/local/bin/python3.14`
- **NÃO usar conda** (removido)

### gh CLI
- Local: `/usr/bin/gh` (v2.46.0)
- Autenticado: `gh auth status` → ZeroBond85
- Token: `~/.config/gh/hosts.yml` (perm 600)

### Git
- Local: `/usr/bin/git` (v2.47.3)
- Line endings: `core.autocrlf=input` (WSL), `true` (Windows)

### Projeto Path
- `/mnt/c/Zerobond/Code/CustoDoce`

### Comandos Validados
```bash
# Validar paridade
wsl -d Debian -e bash -c 'cd /mnt/c/Zerobond/Code/CustoDoce && /usr/local/bin/python3.14 scripts/check_environment_parity.py'

# Rodar workflows
wsl -d Debian -e bash -c 'cd /mnt/c/Zerobond/Code/CustoDoce && gh workflow run ci.yml'

# Monitorar CI
wsl -d Debian -e bash -c 'gh run list --limit 5 --json databaseId,conclusion,status,workflowName'
wsl -d Debian -e bash -c 'gh run view RUN_ID --json conclusion'
```

### Regras de Ouro
1. **Sempre commitar/pushar via WSL** (regra #15 AGENTS.md)
2. **Lock files gerados só no WSL/Linux** (regra #10)
3. **Python 3.14.6 exclusivamente** - nenhuma versão inferior
4. **Paridade total** validada por `check_environment_parity.py`