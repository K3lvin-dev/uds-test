import subprocess
import sys


def format_code():
    """Executa lint com fix e formatação do Ruff."""
    print("--- Executando ruff check --fix ---")
    res1 = subprocess.run(["ruff", "check", "--fix", "."])

    print("\n--- Executando ruff format ---")
    res2 = subprocess.run(["ruff", "format", "."])

    if res1.returncode != 0 or res2.returncode != 0:
        sys.exit(1)

    print("\nFormatacao e correcao concluidas com sucesso.")
