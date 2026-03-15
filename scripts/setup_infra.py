import subprocess
import sys
import time


def run(cmd):
    print(f"Executando: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Erro ao executar: {cmd}")
        sys.exit(1)


def main():
    print("--- Iniciando Infraestrutura ---")

    # 1. Sobe os containers
    run("docker compose up -d")

    # 2. Aguarda healthchecks
    print("Aguardando containers ficarem saudaveis...")
    max_attempts = 30
    for _attempt in range(max_attempts):
        result = subprocess.run(
            "docker compose ps --format '{{.Name}} {{.Health}}'",
            shell=True,
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        healthy_count = sum(
            1
            for line in lines
            if line.strip().endswith("healthy") and "unhealthy" not in line
        )  # noqa: E501
        if healthy_count >= 2:
            break
        time.sleep(2)
    else:
        print("Erro: containers nao ficaram saudaveis a tempo.")
        sys.exit(1)

    print("--- Infraestrutura Pronta ---")


if __name__ == "__main__":
    main()
