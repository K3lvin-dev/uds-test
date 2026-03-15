import subprocess
import sys


def format_code():
    """Executa lint com fix, formatação do Ruff e checagem de tipos com Pyright."""
    print("--- Executando ruff check --fix ---")
    res1 = subprocess.run(["ruff", "check", "--fix", "."])

    print("\n--- Executando ruff format ---")
    res2 = subprocess.run(["ruff", "format", "."])

    print("\n--- Executando pyright ---")
    res3 = subprocess.run(["pyright", "src"])

    if res1.returncode != 0 or res2.returncode != 0 or res3.returncode != 0:
        sys.exit(1)

    print("\nFormatacao, correcao e checagem de tipos concluidas com sucesso.")
