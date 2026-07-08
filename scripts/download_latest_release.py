#!/usr/bin/env python3
"""
Script para baixar o último backup do GitHub Releases.
"""

import os
import sys
import requests


def download_latest_release(repo: str, prefix: str, token: str, output_dir: str) -> bool:
    """Baixa o último backup do GitHub Releases."""
    url = f"https://api.github.com/repos/{repo}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        releases = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar releases: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Detalhes: {e.response.text}", file=sys.stderr)
        return False

    # Filtrar releases com prefixo especificado
    filtered_releases = [r for r in releases if r.get('tag_name', '').startswith(prefix)]
    if not filtered_releases:
        print("Nenhuma release encontrada com prefixo 'backup-'", file=sys.stderr)
        return False

    # Ordenar releases por data (mais recente primeiro)
    filtered_releases.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    latest_release = filtered_releases[0]

    # Baixar arquivos da release
    assets_url = f"{latest_release['url']}/assets"
    try:
        assets_response = requests.get(assets_url, headers=headers)
        assets_response.raise_for_status()
        assets = assets_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar assets: {e}", file=sys.stderr)
        return False

    # Criar diretório de saída
    os.makedirs(output_dir, exist_ok=True)

    # Baixar cada arquivo
    for asset in assets:
        asset_name = asset['name']
        download_url = asset['browser_download_url']
        local_path = os.path.join(output_dir, asset_name)

        try:
            print(f"Baixando {asset_name}...")
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Arquivo {asset_name} baixado com sucesso.")
        except requests.exceptions.RequestException as e:
            print(f"Erro ao baixar {asset_name}: {e}", file=sys.stderr)
            return False

    return True


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Uso: python download_latest_release.py --repo <repo> --prefix <prefix> --token <token> --output-dir <output_dir>")
        sys.exit(1)

    args = sys.argv[1:]
    repo = None
    prefix = None
    token = None
    output_dir = None

    for i in range(0, len(args), 2):
        if i + 1 >= len(args):
            print("Argumentos inválidos.")
            sys.exit(1)

        if args[i] == "--repo":
            repo = args[i+1]
        elif args[i] == "--prefix":
            prefix = args[i+1]
        elif args[i] == "--token":
            token = args[i+1]
        elif args[i] == "--output-dir":
            output_dir = args[i+1]

    if not repo or not prefix or not token or not output_dir:
        print("Todos os argumentos são obrigatórios.")
        sys.exit(1)

    success = download_latest_release(repo, prefix, token, output_dir)
    sys.exit(0 if success else 1)